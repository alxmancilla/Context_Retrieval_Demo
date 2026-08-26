from core.threads import register_thread, scoped_thread_id


class Collection:
    def update_one(self, query, update, upsert=False):
        self.call = (query, update, upsert)


class Database:
    def __init__(self):
        self.collection = Collection()

    def __getitem__(self, _name):
        return self.collection


def test_thread_ids_are_stable_and_scope_sensitive():
    first = scoped_thread_id("realm-a", "alice", "chat-1")
    assert first == scoped_thread_id("realm-a", "alice", "chat-1")
    assert first != scoped_thread_id("realm-b", "alice", "chat-1")
    assert first != scoped_thread_id("realm-a", "bob", "chat-1")


def test_thread_registration_records_owner_and_expiry():
    database = Database()
    register_thread(database, "thread-1", "realm", "user", 7)
    query, update, upsert = database.collection.call
    assert query == {"thread_id": "thread-1"}
    assert update["$set"]["realm_id"] == "realm"
    assert update["$set"]["user_id"] == "user"
    assert update["$set"]["expires_at"] > update["$set"]["updated_at"]
    assert upsert is True