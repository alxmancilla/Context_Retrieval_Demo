from db import bootstrap as bootstrap_module


class FakeAdmin:
    def __init__(self) -> None:
        self.commands = []

    def command(self, name: str) -> None:
        self.commands.append(name)


class FakeClient:
    def __init__(self, uri: str, **kwargs) -> None:
        self.uri = uri
        self.kwargs = kwargs
        self.admin = FakeAdmin()

    def __getitem__(self, name: str):
        return {"database": name}


def test_connect_applies_bounded_demo_timeouts(monkeypatch):
    monkeypatch.setattr(bootstrap_module, "MongoClient", FakeClient)
    client, database = bootstrap_module.connect(
        "mongodb://example", "demo", server_selection_timeout_ms=5,
        connect_timeout_ms=10, socket_timeout_ms=60,
    )
    assert client.kwargs["serverSelectionTimeoutMS"] == 5
    assert client.kwargs["connectTimeoutMS"] == 10
    assert client.kwargs["socketTimeoutMS"] == 60
    assert client.admin.commands == ["ping"]
    assert database == {"database": "demo"}
