import hashlib
from datetime import UTC, datetime, timedelta

from pymongo.database import Database

from core.schemas import THREAD_OWNERSHIP_COLLECTION


def scoped_thread_id(realm_id: str, user_id: str, external_id: str) -> str:
    digest = hashlib.sha256(
        f"{realm_id}\0{user_id}\0{external_id}".encode()
    ).hexdigest()
    return f"thread-{digest}"


def register_thread(
    db: Database, thread_id: str, realm_id: str, user_id: str, retention_days: int,
) -> None:
    now = datetime.now(UTC)
    db[THREAD_OWNERSHIP_COLLECTION].update_one(
        {"thread_id": thread_id},
        {"$set": {
            "thread_id": thread_id, "realm_id": realm_id, "user_id": user_id,
            "updated_at": now, "expires_at": now + timedelta(days=retention_days),
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )