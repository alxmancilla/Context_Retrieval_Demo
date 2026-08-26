from core.schemas import THREAD_OWNERSHIP_COLLECTION
from scripts.delete_tenant import TENANT_COLLECTIONS, delete_tenant


class Result:
    deleted_count = 2


class Collection:
    def __init__(self, threads=None):
        self.threads = threads or []
        self.queries = []

    def find(self, query, _projection):
        self.queries.append(query)
        return self.threads

    def delete_many(self, query):
        self.queries.append(query)
        return Result()


class Database:
    def __init__(self):
        self.collections = {
            name: Collection() for name in (
                *TENANT_COLLECTIONS, THREAD_OWNERSHIP_COLLECTION,
                "checkpoints", "checkpoint_writes",
            )
        }
        self.collections[THREAD_OWNERSHIP_COLLECTION].threads = [
            {"thread_id": "thread-a"}, {"thread_id": "thread-b"},
        ]

    def __getitem__(self, name):
        return self.collections[name]


def test_tenant_deletion_scopes_every_collection_and_owned_checkpoint():
    database = Database()
    counts = delete_tenant(database, "realm-a")
    assert set(counts) == {
        *TENANT_COLLECTIONS, THREAD_OWNERSHIP_COLLECTION,
        "checkpoints", "checkpoint_writes",
    }
    for name in TENANT_COLLECTIONS:
        assert database[name].queries == [{"realm_id": "realm-a"}]
    assert database["checkpoints"].queries == [{
        "thread_id": {"$in": ["thread-a", "thread-b"]}
    }]