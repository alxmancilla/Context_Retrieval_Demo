"""Exercise the asynchronous graph path used by the Chainlit UI."""

import asyncio
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.mongodb import MongoDBSaver

from agent.graph import build_graph
from agent.nodes import AgentNodes
from core.observability import configure_logging
from core.providers.chat import GroveChatProvider
from core.providers.rerank import create_voyage_reranker
from core.settings import get_settings
from db.bootstrap import connect


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    client, db = connect(
        settings.mongodb_uri,
        settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
        max_pool_size=settings.mongodb_max_pool_size,
        min_pool_size=settings.mongodb_min_pool_size,
        wait_queue_timeout_ms=settings.mongodb_wait_queue_timeout_ms,
    )
    try:
        chat = GroveChatProvider(
            api_key=settings.grove_api_key,
            base_url=settings.grove_base_url,
            model=settings.grove_model,
            timeout_seconds=settings.grove_timeout_seconds,
            max_retries=settings.grove_max_retries,
        )
        graph = build_graph(
            AgentNodes(
                db, chat, settings.source_top_k, settings.memory_top_k,
                settings.memory_retention_days, settings.memory_max_per_user,
                memory_min_importance=settings.memory_min_importance,
                memory_similarity_threshold=settings.memory_similarity_threshold,
                memory_embedding_profile=settings.memory_embedding_profile,
                prompt_version=settings.prompt_version,
                agent_version=settings.agent_version,
                recent_context_messages=settings.recent_context_messages,
                recent_context_max_chars=settings.recent_context_max_chars,
                conversation_summary_max_chars=settings.conversation_summary_max_chars,
                reconciliation_weights=settings.reconciliation_weights,
                reranker=create_voyage_reranker(
                    api_key=settings.voyage_api_key,
                    model=settings.voyage_rerank_model,
                    timeout_seconds=settings.voyage_rerank_timeout_seconds,
                    max_retries=settings.voyage_rerank_max_retries,
                ),
            ),
            MongoDBSaver(
                client, db_name=settings.mongodb_db,
                ttl=settings.checkpoint_retention_days * 86400,
            ),
        )
        config = {"configurable": {"thread_id": "chainlit-live-smoke"}}
        question = "What is the eligibility cache TTL, and why did it change?"
        graph_input = {
            "query": question,
            "messages": [HumanMessage(content=question)],
            "realm_id": settings.realm_id,
            "user_id": settings.user_id,
            "access_principals": list(settings.access_principals),
            "correlation_id": str(uuid4()),
        }
        seen, token_events = [], 0
        async for mode, chunk in graph.astream(
            graph_input, config=config, stream_mode=["updates", "custom"]
        ):
            if mode == "custom" and chunk.get("event") == "answer_token":
                token_events += 1
            elif mode == "updates":
                seen.extend(chunk.keys())
        state = (await graph.aget_state(config)).values
        print("nodes=", sorted(set(seen)))
        print("sources=", sorted(state.get("source_results", {})))
        print("contradictions=", len(state.get("contradictions", [])))
        print("streamed_tokens=", token_events)
        print("has_sources_section=", "### Sources" in state.get("answer", ""))
        print("degraded=", state.get("degraded", []))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
