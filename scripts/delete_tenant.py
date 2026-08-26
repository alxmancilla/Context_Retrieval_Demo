import argparse
import json

from core.schemas import (
    ALL_SOURCES,
    CLAIM_ASSERTIONS_COLLECTION,
    GOVERNANCE_COLLECTION,
    THREAD_OWNERSHIP_COLLECTION,
)
from core.settings import get_settings
from db.bootstrap import connect

TENANT_COLLECTIONS = (
    *ALL_SOURCES, "sources", GOVERNANCE_COLLECTION,
    CLAIM_ASSERTIONS_COLLECTION, "memories",
)


def delete_tenant(db, realm_id: str) -> dict[str, int]:
    thread_ids = [
        row["thread_id"]
        for row in db[THREAD_OWNERSHIP_COLLECTION].find(
            {"realm_id": realm_id}, {"_id": 0, "thread_id": 1}
        )
    ]
    counts = {
        name: db[name].delete_many({"realm_id": realm_id}).deleted_count
        for name in TENANT_COLLECTIONS
    }
    for name in ("checkpoints", "checkpoint_writes"):
        counts[name] = db[name].delete_many(
            {"thread_id": {"$in": thread_ids}}
        ).deleted_count if thread_ids else 0
    counts[THREAD_OWNERSHIP_COLLECTION] = db[THREAD_OWNERSHIP_COLLECTION].delete_many(
        {"realm_id": realm_id}
    ).deleted_count
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete one tenant's application data")
    parser.add_argument("--realm-id", required=True)
    parser.add_argument("--confirm-realm", required=True)
    args = parser.parse_args()
    if args.confirm_realm != args.realm_id:
        raise SystemExit("--confirm-realm must exactly match --realm-id")
    settings = get_settings()
    client, db = connect(
        settings.mongodb_uri, settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
        max_pool_size=settings.mongodb_max_pool_size,
        min_pool_size=settings.mongodb_min_pool_size,
        wait_queue_timeout_ms=settings.mongodb_wait_queue_timeout_ms,
    )
    try:
        counts = delete_tenant(db, args.realm_id)
        print(json.dumps({"realm_id": args.realm_id, "deleted": counts}, sort_keys=True))
    finally:
        client.close()


if __name__ == "__main__":
    main()