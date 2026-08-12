"""Validate Atlas principal filtering without printing document content."""

from core.settings import get_settings
from core.source_agents import SOURCE_VECTOR_INDEX, SourceAgent
from db.bootstrap import connect


def main() -> None:
    settings = get_settings()
    client, db = connect(
        settings.mongodb_uri,
        settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    try:
        agent = SourceAgent(db.github, "github", 5)
        allowed = agent.search(
            "PHI logging and audit controls", settings.realm_id, ["role:security"]
        )
        denied = agent.search(
            "PHI logging and audit controls", settings.realm_id, ["role:unknown"]
        )
        index = list(db.github.list_search_indexes(SOURCE_VECTOR_INDEX))[0]
        definition = index.get("latestDefinition") or index.get("definition") or {}
        fields = [
            (field.get("type"), field.get("path"))
            for field in definition.get("fields", [])
        ]
        acl_documents = db.github.count_documents({
            "realm_id": settings.realm_id,
            "access_principals": {"$exists": True},
        })
        print("acl_documents=", acl_documents)
        print("security_results=", len(allowed))
        print("security_themes=", sorted({row["metadata"].get("theme") for row in allowed}))
        print("unknown_results=", len(denied))
        print("index_status=", index.get("status"))
        print("index_fields=", fields)
        if acl_documents != 128 or not allowed or denied or index.get("status") != "READY":
            raise SystemExit("ACL diagnostic failed")
    finally:
        client.close()


if __name__ == "__main__":
    main()