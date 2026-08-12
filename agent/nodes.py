from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from pymongo.database import Database

from agent.prompts import ANSWER_SYSTEM, INTENT_SYSTEM, answer_prompt
from core.citations import bind_source_links
from core.memory import SemanticMemory
from core.observability import get_logger, log_event, log_failure
from core.providers.chat import GroveChatProvider
from core.providers.rerank import VoyageReranker
from core.reconciliation import DEFAULT_RECONCILIATION_WEIGHTS, ReconciliationWeights, reconcile
from core.schemas import ALL_SOURCES, AgentState, Intent, SourceName
from core.source_agents import SourceAgent

LOGGER = get_logger("agent.nodes")


class AgentNodes:
    reconciliation_weights = DEFAULT_RECONCILIATION_WEIGHTS
    reranker: VoyageReranker | None = None

    def __init__(self, db: Database, chat: GroveChatProvider, source_top_k: int,
                 memory_top_k: int, memory_retention_days: int = 30,
                 memory_max_per_user: int = 100,
                 reconciliation_weights: ReconciliationWeights = DEFAULT_RECONCILIATION_WEIGHTS,
                 reranker: VoyageReranker | None = None,
                 ) -> None:
        self.db = db
        self.chat = chat
        self.memory = SemanticMemory(
            db.memories, memory_top_k, memory_retention_days, memory_max_per_user
        )
        self.reconciliation_weights = reconciliation_weights
        self.reranker = reranker
        self.agents = {
            source: SourceAgent(db[source], source, source_top_k) for source in ALL_SOURCES
        }

    def parse_intent(self, state: AgentState) -> dict:
        query = state["query"]
        try:
            intent = self.chat.invoke_typed(INTENT_SYSTEM, query, Intent)
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
            return {"memories": rows}
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
                query, state["realm_id"], state.get("access_principals", ["public"])
            )
            return {"source_results": {source: rows}}
        except Exception as exc:
            degraded = f"retrieve_{source}:{type(exc).__name__}"
            log_failure(
                LOGGER, "source_degraded", exc,
                correlation_id=state.get("correlation_id"), node="retrieve_source",
                source=source, degraded=degraded,
            )
            return {
                "source_results": {source: []},
                "degraded": [degraded],
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
        degraded = []
        for source in missing_sources:
            marker = f"source_registry_missing:{source}"
            degraded.append(marker)
            log_event(
                LOGGER, 30, "source_registry_missing",
                correlation_id=state.get("correlation_id"), node="reconcile",
                source=source, degraded=marker,
            )
        trusted_results = {
            source: hits for source, hits in results.items() if source in registry
        }
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
            state.get("memories", []),
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
            self.memory.save(
                f"Question: {state['query']}\nAnswer: {state['answer'][:2500]}",
                state["realm_id"], state["user_id"], state["correlation_id"],
            )
            return {}
        except Exception as exc:
            degraded = f"memory_save:{type(exc).__name__}"
            log_failure(
                LOGGER, "node_degraded", exc,
                correlation_id=state.get("correlation_id"), node="save_memory",
                degraded=degraded,
            )
            return {"degraded": [degraded]}
