import asyncio
from types import SimpleNamespace

import chainlit_app
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


def test_chainlit_runtime_is_built_once_and_reused(monkeypatch):
    calls = []
    runtime = chainlit_app.AppRuntime(
        client=SimpleNamespace(close=lambda: None), graph=object(), settings=SimpleNamespace()
    )

    async def run_sync(function, *args):
        return function(*args)

    monkeypatch.setattr(chainlit_app, "_RUNTIME", None)
    monkeypatch.setattr(chainlit_app, "_RUNTIME_LOCK", asyncio.Lock())
    monkeypatch.setattr(chainlit_app, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(chainlit_app.cl, "make_async", lambda function: lambda *args: run_sync(function, *args))
    monkeypatch.setattr(
        chainlit_app, "_build_runtime", lambda _settings: calls.append("build") or runtime
    )

    async def get_twice():
        return await chainlit_app._get_runtime(), await chainlit_app._get_runtime()

    first, second = asyncio.run(get_twice())
    assert first is second is runtime
    assert calls == ["build"]
    monkeypatch.setattr(chainlit_app, "_RUNTIME", None)
