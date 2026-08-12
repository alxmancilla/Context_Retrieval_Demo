"""Validate retention indexes and migration metadata without reading content."""

from core.memory import MEMORY_VECTOR_INDEX
from core.settings import get_settings
from db.bootstrap import connect


def _ttl_indexes(collection) -> list[tuple[str, int]]:
    return [
        (index["name"], index["expireAfterSeconds"])
        for index in collection.list_indexes()
        if "expireAfterSeconds" in index
    ]


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
        expected_checkpoint_ttl = settings.checkpoint_retention_days * 86400
        memory_indexes = list(db.memories.list_search_indexes(MEMORY_VECTOR_INDEX))
        memory_status = memory_indexes[0].get("status") if memory_indexes else "MISSING"
        memory_ttl = _ttl_indexes(db.memories)
        checkpoint_ttl = _ttl_indexes(db.checkpoints)
        writes_ttl = _ttl_indexes(db.checkpoint_writes)
        missing_memory_expiry = db.memories.count_documents({"expires_at": {"$exists": False}})
        missing_checkpoint_time = sum(
            db[name].count_documents({"created_at": {"$exists": False}})
            for name in ("checkpoints", "checkpoint_writes")
        )
        print("memory_vector_status=", memory_status)
        print("memory_ttl=", memory_ttl)
        print("checkpoint_ttl=", checkpoint_ttl)
        print("checkpoint_writes_ttl=", writes_ttl)
        print("missing_memory_expiry=", missing_memory_expiry)
        print("missing_checkpoint_created_at=", missing_checkpoint_time)
        valid = (
            memory_status == "READY"
            and any(seconds == 0 for _, seconds in memory_ttl)
            and any(seconds == expected_checkpoint_ttl for _, seconds in checkpoint_ttl)
            and any(seconds == expected_checkpoint_ttl for _, seconds in writes_ttl)
            and missing_memory_expiry == 0
            and missing_checkpoint_time == 0
        )
        if not valid:
            raise SystemExit("Retention diagnostic failed")
    finally:
        client.close()


if __name__ == "__main__":
    main()