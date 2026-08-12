from types import SimpleNamespace

import pytest

from core.providers.rerank import voyage as voyage_module
from core.providers.rerank.voyage import VoyageReranker, create_voyage_reranker


def _hits() -> list[dict]:
    return [
        {"source": "github", "title": "Current auth", "content": "OAuth 2 with PKCE"},
        {"source": "teams", "title": "Old auth", "content": "OAuth 1 signatures"},
    ]


def test_voyage_reranker_configures_client_and_aligns_scores(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def rerank(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(results=[
                SimpleNamespace(index=1, relevance_score=0.2),
                SimpleNamespace(index=0, relevance_score=0.9),
            ])

    monkeypatch.setattr(voyage_module, "Client", FakeClient)
    provider = VoyageReranker(
        api_key="redacted", model="rerank-2.5", timeout_seconds=8.0, max_retries=3
    )
    reranked = provider.rerank("current authentication", _hits())

    assert captured["client"] == {
        "api_key": "redacted", "timeout": 8.0, "max_retries": 3,
    }
    assert captured["request"]["model"] == "rerank-2.5"
    assert captured["request"]["top_k"] is None
    assert "Current auth" in captured["request"]["documents"][0]
    assert [hit["rerank_score"] for hit in reranked] == [0.9, 0.2]


def test_voyage_reranker_rejects_incomplete_results():
    provider = object.__new__(VoyageReranker)
    provider.model = "rerank-2.5"
    provider.client = SimpleNamespace(rerank=lambda **_kwargs: SimpleNamespace(results=[]))
    with pytest.raises(ValueError, match="did not score every document"):
        provider.rerank("query", _hits())


def test_reranker_factory_is_disabled_without_a_key():
    assert create_voyage_reranker(
        api_key=None, model="rerank-2.5", timeout_seconds=15, max_retries=2
    ) is None