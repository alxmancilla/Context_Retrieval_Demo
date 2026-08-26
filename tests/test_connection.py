import asyncio
import json
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
    assert client.kwargs["maxPoolSize"] == 50
    assert client.kwargs["minPoolSize"] == 0
    assert client.kwargs["waitQueueTimeoutMS"] == 5000
    assert client.admin.commands == ["ping"]
    assert database == {"database": "demo"}


def test_chainlit_runtime_is_built_once_and_reused(monkeypatch):
    calls = []
    runtime = chainlit_app.AppRuntime(
        client=SimpleNamespace(close=lambda: None), database=object(),
        graph=object(), settings=SimpleNamespace(),
        pool_metrics=SimpleNamespace(snapshot=lambda: {}),
        memory_metrics=SimpleNamespace(snapshot=lambda: {}),
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


def test_readiness_requires_all_mongodb_search_indexes(monkeypatch):
    client = SimpleNamespace(admin=FakeAdmin())
    runtime = chainlit_app.AppRuntime(
        client=client, database=object(), graph=object(), settings=SimpleNamespace(),
        pool_metrics=SimpleNamespace(snapshot=lambda: {"checked_out": 1}),
        memory_metrics=SimpleNamespace(snapshot=lambda: {"write_rejected": 2}),
    )
    monkeypatch.setattr(
        chainlit_app, "search_index_statuses",
        lambda _db: {f"index-{index}": "READY" for index in range(11)},
    )
    snapshot = chainlit_app._readiness_snapshot(runtime)
    assert snapshot["status"] == "ready"
    assert snapshot["search_indexes_ready"] == 11
    assert snapshot["pool"] == {"checked_out": 1}
    assert snapshot["memory"] == {"write_rejected": 2}
    assert snapshot["versions"] == {
        "agent": "unknown", "prompt": "unknown", "memory_embedding": "unknown",
    }


def test_probe_middleware_intercepts_chainlit_spa_routes(monkeypatch):
    async def fail_fallback(_request):
        raise AssertionError("probe reached SPA fallback")

    async def ready():
        return chainlit_app.JSONResponse(content={"status": "ready"})

    monkeypatch.setattr(chainlit_app, "readiness", ready)
    health = asyncio.run(chainlit_app.operational_probe(
        SimpleNamespace(url=SimpleNamespace(path="/health")), fail_fallback,
    ))
    readiness = asyncio.run(chainlit_app.operational_probe(
        SimpleNamespace(url=SimpleNamespace(path="/ready")), fail_fallback,
    ))
    assert json.loads(health.body) == {"status": "healthy"}
    assert json.loads(readiness.body) == {"status": "ready"}
