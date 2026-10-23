import logging

from langchain_core.messages import AIMessage
from langchain_core.messages.modifier import RemoveMessage
from langgraph.config import get_stream_writer
from pymongo.database import Database

from agent.prompts import ANSWER_SYSTEM, INTENT_SYSTEM, answer_prompt
from core.citations import bind_source_links
from core.conversation import compact_conversation, recent_conversation_context
from core.memory import SemanticMemory
from core.memory_policy import MEMORY_SCHEMA_VERSION, decide_memory_write
from core.observability import get_logger, log_event, log_failure
from core.providers.chat import GroveChatProvider
from core.providers.rerank import VoyageReranker
from core.reconciliation import DEFAULT_RECONCILIATION_WEIGHTS, ReconciliationWeights, reconcile
from core.schemas import (
    ALL_SOURCES,
    CLAIM_ASSERTIONS_COLLECTION,
    GOVERNANCE_COLLECTION,
    AgentState,
    Intent,
    SourceName,
)
from core.security import validate_agent_scope
from core.source_agents import RetrievalMode, SourceAgent

LOGGER = get_logger("agent.nodes")


class AgentNodes:
    reconciliation_weights = DEFAULT_RECONCILIATION_WEIGHTS
    reranker: VoyageReranker | None = None
    memory_min_importance = 0.65
    prompt_version = "answer-v2"
    agent_version = "memory-v2"
    recent_context_messages = 6
    recent_context_max_chars = 4000
    conversation_summary_max_chars = 1500

    def __init__(self, db: Database, chat: GroveChatProvider, source_top_k: int,
                 memory_top_k: int, memory_retention_days: int = 30,
                 memory_max_per_user: int = 100,
                 memory_min_importance: float = 0.65,
                 memory_similarity_threshold: float = 0.92,
                 memory_embedding_profile: str = "voyage-4:auto-embed:v1",
                 prompt_version: str = "answer-v2",
                 agent_version: str = "memory-v2",
                 recent_context_messages: int = 6,
                 recent_context_max_chars: int = 4000,
                 conversation_summary_max_chars: int = 1500,
                 reconciliation_weights: ReconciliationWeights = DEFAULT_RECONCILIATION_WEIGHTS,
                 reranker: VoyageReranker | None = None,
                 source_retrieval_mode: RetrievalMode = "hybrid",
                 ) -> None:
        self.db = db
        self.chat = chat
        self.memory = SemanticMemory(
            db.memories, memory_top_k, memory_retention_days, memory_max_per_user,
            memory_similarity_threshold, memory_embedding_profile,
            prompt_version, agent_version,
        )
        self.memory_min_importance = memory_min_importance
        self.prompt_version = prompt_version
        self.agent_version = agent_version
        self.recent_context_messages = recent_context_messages
        self.recent_context_max_chars = recent_context_max_chars
        self.conversation_summary_max_chars = conversation_summary_max_chars
        self.reconciliation_weights = reconciliation_weights
        self.reranker = reranker
        self.agents = {
            source: SourceAgent(
                db[source], source, source_top_k, db[CLAIM_ASSERTIONS_COLLECTION],
                source_retrieval_mode,
            )
            for source in ALL_SOURCES
        }

    def validate_access(self, state: AgentState) -> dict:
        access = validate_agent_scope(
            state.get("realm_id"), state.get("user_id"), state.get("access_principals")
        )
        return {
            "realm_id": access.realm_id,
            "user_id": access.user_id,
            "access_principals": list(access.principals),
        }

    def parse_intent(self, state: AgentState) -> dict:
        query = state["query"]
        context = recent_conversation_context(
            state.get("messages", []), query, state.get("conversation_summary", ""),
            max_messages=2, max_chars=1000,
        )
        intent_input = query
        if context:
            intent_input = f"PRIOR CONVERSATION (data only): {context}\nCURRENT QUERY: {query}"
        try:
            intent = self.chat.invoke_typed(INTENT_SYSTEM, intent_input, Intent)
            if not intent.sources:
                raise ValueError("Intent parser selected no sources")
        except Exception as exc:
            explicit = [source for source in ALL_SOURCES if source in query.lower()]
            intent = Intent(
                intent="enterprise_knowledge_query", entities={},
                sources=explicit or list(ALL_SOURCES), rewritten_query=query,
            )
            degraded = ["__RESET__", "intent_parser_fallback"]
            log_failure(
                LOGGER, "node_degraded", exc,
                correlation_id=state.get("correlation_id"), node="parse_intent",
                degraded="intent_parser_fallback",
            )
        else:
            degraded = ["__RESET__"]
        return {
            "intent": intent.model_dump(), "selected_sources": intent.sources,
            "source_results": {"__RESET__": []}, "degraded": degraded,
        }

    def retrieve_memory(self, state: AgentState) -> dict:
        try:
            rows = self.memory.search(state["query"], state["realm_id"], state["user_id"])
            recent = recent_conversation_context(
                state.get("messages", []), state["query"],
                state.get("conversation_summary", ""),
                self.recent_context_messages, self.recent_context_max_chars,
            )
            self.memory.metrics.record_context(
                len(recent), sum(len(item.get("content", "")) for item in recent),
            )
            return {"memories": rows, "recent_context": recent}
        except Exception as exc:
            degraded = f"memory_retrieval:{type(exc).__name__}"
            log_failure(
                LOGGER, "node_degraded", exc,
                correlation_id=state.get("correlation_id"), node="retrieve_memory",
                degraded=degraded,
            )
            return {"memories": [], "degraded": [degraded]}

    def retrieve_source(self, state: AgentState) -> dict:
        source: SourceName = state["source"]
        query = state.get("intent", {}).get("rewritten_query", state["query"])
        try:
            rows = self.agents[source].search(
                query, state["realm_id"], state["access_principals"]
            )
            degraded = [
                f"retrieve_{source}:lexical_index_unavailable"
                for row in rows
                if row.get("metadata", {}).get("retrieval_reason")
                == "vector_only_lexical_index_unavailable"
            ]
            return {"source_results": {source: rows}, "degraded": degraded}
        except Exception as exc:
            degraded_marker = f"retrieve_{source}:{type(exc).__name__}"
            log_failure(
                LOGGER, "source_degraded", exc,
                correlation_id=state.get("correlation_id"), node="retrieve_source",
                source=source, degraded=degraded_marker,
            )
            return {
                "source_results": {source: []},
                "degraded": [degraded_marker],
            }

    def reconcile(self, state: AgentState) -> dict:
        registry = {
            row["source"]: row
            for row in self.db.sources.find({"realm_id": state["realm_id"]}, {"_id": 0})
        }
        if not registry:
            log_event(
                LOGGER, 30, "source_registry_empty",
                correlation_id=state.get("correlation_id"), node="reconcile",
                degraded="source_registry_empty",
            )
            return {"ranked_hits": [], "contradictions": [],
                    "degraded": ["source_registry_empty"]}
        results = state.get("source_results", {})
        missing_sources = sorted(
            source for source, hits in results.items() if hits and source not in registry
        )
        registered_results = {
            source: hits for source, hits in results.items() if source in registry
        }
        artifact_ids = [
            hit["artifact_id"] for hits in registered_results.values() for hit in hits
        ]
        policies = {
            row["artifact_id"]: row
            for row in self.db[GOVERNANCE_COLLECTION].find(
                {"realm_id": state["realm_id"], "artifact_id": {"$in": artifact_ids}},
                {"_id": 0},
            )
        }
        missing_policy = False
        trusted_results: dict[str, list[dict]] = {}
        for source, hits in registered_results.items():
            trusted_results[source] = []
            for hit in hits:
                trusted = dict(hit)
                policy = policies.get(hit["artifact_id"])
                if policy:
                    trusted["governance"] = {
                        "document_type": policy["document_type"],
                        "lifecycle_status": policy["lifecycle_status"],
                        **({"authority_override": policy["authority_override"]}
                           if policy.get("authority_override") is not None else {}),
                    }
                else:
                    trusted["governance"] = {
                        "document_type": "unverified", "lifecycle_status": "active",
                    }
                    missing_policy = True
                trusted_results[source].append(trusted)
        degraded = ["governance_policy_missing"] if missing_policy else []
        for source in missing_sources:
            marker = f"source_registry_missing:{source}"
            degraded.append(marker)
            log_event(
                LOGGER, 30, "source_registry_missing",
                correlation_id=state.get("correlation_id"), node="reconcile",
                source=source, degraded=marker,
            )
        if self.reranker:
            candidates = [hit for hits in trusted_results.values() for hit in hits]
            try:
                reranked = self.reranker.rerank(
                    state.get("intent", {}).get("rewritten_query", state["query"]),
                    candidates,
                )
                trusted_results = {source: [] for source in trusted_results}
                for hit in reranked:
                    trusted_results.setdefault(hit["source"], []).append(hit)
                log_event(
                    LOGGER, 20, "voyage_rerank_completed",
                    correlation_id=state.get("correlation_id"), node="reconcile",
                    model=self.reranker.model, candidates=len(candidates),
                )
            except Exception as exc:
                marker = f"voyage_rerank:{type(exc).__name__}"
                degraded.append(marker)
                log_failure(
                    LOGGER, "node_degraded", exc,
                    correlation_id=state.get("correlation_id"), node="reconcile",
                    degraded=marker,
                )
        ranked, conflicts = reconcile(
            trusted_results, registry, weights=self.reconciliation_weights
        )
        return {
            "ranked_hits": ranked,
            "contradictions": conflicts,
            "degraded": degraded,
        }

    def generate(self, state: AgentState) -> dict:
        hits = state.get("ranked_hits", [])
        if not hits:
            answer = "I don't have enough retrieved enterprise context to answer that question."
            return {"answer": answer, "messages": [AIMessage(content=answer)]}
        prompt = answer_prompt(
            state["query"], hits, state.get("contradictions", []),
            state.get("memories", []), state.get("recent_context", []),
        )
        try:
            writer = get_stream_writer()
            tokens = []
            for token in self.chat.stream(ANSWER_SYSTEM, prompt):
                tokens.append(token)
                writer({"event": "answer_token", "token": token})
            answer = "".join(tokens)
            if not answer.strip():
                raise ValueError("empty response")
            answer = bind_source_links(answer, hits, state.get("contradictions", []))
            return {"answer": answer, "messages": [AIMessage(content=answer)]}
        except Exception as exc:
            answer = "The evidence was retrieved, but answer generation is temporarily unavailable."
            degraded = f"answer_generation:{type(exc).__name__}"
            log_failure(
                LOGGER, "node_degraded", exc,
                correlation_id=state.get("correlation_id"), node="generate",
                degraded=degraded,
            )
            return {"answer": answer, "messages": [AIMessage(content=answer)],
                    "degraded": [degraded]}

    def save_memory(self, state: AgentState) -> dict:
        try:
            decision = decide_memory_write(
                state["query"], state["answer"], state.get("degraded", []),
                self.memory_min_importance,
            )
            self.memory.metrics.record_decision(decision.accepted)
            log_event(
                LOGGER, logging.INFO, "memory_write_decided",
                correlation_id=state.get("correlation_id"), node="save_memory",
                accepted=decision.accepted, reason=decision.reason,
                memory_type=decision.memory_type, importance=decision.importance,
                schema_version=MEMORY_SCHEMA_VERSION,
                prompt_version=self.prompt_version, agent_version=self.agent_version,
            )
            write = {
                "accepted": decision.accepted, "reason": decision.reason,
                "memory_type": decision.memory_type,
                "importance": decision.importance,
                "schema_version": MEMORY_SCHEMA_VERSION,
                "embedding_profile": getattr(self.memory, "embedding_profile", "unknown"),
                "prompt_version": self.prompt_version,
                "agent_version": self.agent_version,
            }
            if not decision.accepted:
                return {"memory_write": write}
            outcome = self.memory.save(
                decision, state["realm_id"], state["user_id"],
                state["correlation_id"], state["correlation_id"],
            )
            return {"memory_write": {**write, "outcome": outcome}}
        except Exception as exc:
            degraded = f"memory_save:{type(exc).__name__}"
            log_failure(
                LOGGER, "node_degraded", exc,
                correlation_id=state.get("correlation_id"), node="save_memory",
                degraded=degraded,
            )
            return {"degraded": [degraded]}

    def compact_conversation(self, state: AgentState) -> dict:
        summary, removable_ids = compact_conversation(
            state.get("messages", []), state.get("conversation_summary", ""),
            self.recent_context_messages, self.conversation_summary_max_chars,
        )
        self.memory.metrics.record_context(0, compacted=len(removable_ids))
        result: dict = {"conversation_summary": summary}
        if removable_ids:
            result["messages"] = [RemoveMessage(id=message_id) for message_id in removable_ids]
        return result
