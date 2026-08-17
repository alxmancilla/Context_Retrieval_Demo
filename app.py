import argparse
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.mongodb import MongoDBSaver

from agent.graph import build_graph
from agent.nodes import AgentNodes
from core.memory import SemanticMemory
from core.observability import configure_logging
from core.providers.chat import GroveChatProvider
from core.providers.rerank import create_voyage_reranker
from core.settings import get_settings
from db.bootstrap import bootstrap, connect, wait_for_indexes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CMM AI Context Platform Assistant demo")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("bootstrap", help="Seed Atlas and create autoEmbed indexes")
    setup.add_argument("--wait", action="store_true", help="Wait for all indexes to be READY")
    ask = commands.add_parser("ask", help="Ask one grounded enterprise question")
    ask.add_argument("question")
    ask.add_argument("--thread-id", default="demo-thread")
    forget = commands.add_parser("forget", help="Tombstone this user's semantic memories")
    forget.add_argument("--user-id", default=None)
    forget.add_argument("--confirm", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "forget" and not args.confirm:
        raise SystemExit("Memory deletion requires --confirm")
    settings = get_settings()
    configure_logging(settings.log_level)
    client, db = connect(
        settings.mongodb_uri,
        settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    try:
        if args.command == "bootstrap":
            result = bootstrap(
                db, settings.realm_id,
                memory_retention_days=settings.memory_retention_days,
                checkpoint_retention_days=settings.checkpoint_retention_days,
            )
            MongoDBSaver(
                client, db_name=settings.mongodb_db,
                ttl=settings.checkpoint_retention_days * 86400,
            )
            print(f"Seeded {result['artifacts']} artifacts: {result['per_source']}")
            print(f"Search index actions: {result['search_index_actions']}")
            if args.wait:
                print(f"Index status: {wait_for_indexes(db)}")
            return
        if args.command == "forget":
            user_id = args.user_id or settings.user_id
            deleted = SemanticMemory(db.memories).delete_user(settings.realm_id, user_id)
            print(f"Tombstoned {deleted} semantic memories for user {user_id}.")
            return
        chat = GroveChatProvider(
            api_key=settings.grove_api_key, base_url=settings.grove_base_url,
            model=settings.grove_model, timeout_seconds=settings.grove_timeout_seconds,
            max_retries=settings.grove_max_retries,
        )
        nodes = AgentNodes(
            db, chat, settings.source_top_k, settings.memory_top_k,
            settings.memory_retention_days, settings.memory_max_per_user,
            reconciliation_weights=settings.reconciliation_weights,
            reranker=create_voyage_reranker(
                api_key=settings.voyage_api_key,
                model=settings.voyage_rerank_model,
                timeout_seconds=settings.voyage_rerank_timeout_seconds,
                max_retries=settings.voyage_rerank_max_retries,
            ),
        )
        saver = MongoDBSaver(
            client, db_name=settings.mongodb_db,
            ttl=settings.checkpoint_retention_days * 86400,
        )
        graph = build_graph(nodes, saver)
        correlation_id = str(uuid4())
        result = graph.invoke({
            "query": args.question, "messages": [HumanMessage(content=args.question)],
            "realm_id": settings.realm_id, "user_id": settings.user_id,
            "access_principals": list(settings.access_principals),
            "correlation_id": correlation_id,
        }, config={"configurable": {"thread_id": args.thread_id}})
        print(result["answer"])
        if result.get("degraded"):
            print(f"\n[degraded: {', '.join(result['degraded'])}]")
    finally:
        client.close()


if __name__ == "__main__":
    main()
