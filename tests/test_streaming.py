from datetime import UTC, datetime
from types import SimpleNamespace

from langgraph.graph import END, START, StateGraph

from agent.nodes import AgentNodes
from core.providers.chat import grove as grove_module
from core.providers.chat.grove import GroveChatProvider
from core.schemas import AgentState


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["stream"] is True
        return [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="OAuth "))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="2 [github:gh-auth]"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        ]


def test_grove_provider_applies_explicit_timeout_and_retries(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(grove_module, "OpenAI", fake_openai)
    provider = GroveChatProvider(
        api_key="redacted", base_url="https://grove.example/v1/", model="test-model",
        timeout_seconds=12.5, max_retries=3,
    )
    assert provider.model == "test-model"
    assert captured["base_url"] == "https://grove.example/v1"
    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 3


def test_grove_provider_yields_non_empty_deltas():
    provider = object.__new__(GroveChatProvider)
    provider.model = "test-model"
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    assert list(provider.stream("system", "user")) == [
        "OAuth ", "2 [github:gh-auth]"
    ]


def test_generate_emits_custom_tokens_and_finalizes_citations():
    nodes = object.__new__(AgentNodes)
    nodes.chat = SimpleNamespace(
        stream=lambda _system, _user: iter(["OAuth ", "2 [github:gh-auth]"])
    )
    builder = StateGraph(AgentState)
    builder.add_node("generate", nodes.generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    graph = builder.compile()
    hit = {
        "artifact_id": "gh-auth", "source": "github", "title": "Current auth",
        "content": "OAuth 2", "url": "https://demo/gh-auth",
        "updated_at": datetime.now(UTC), "vector_score": 0.9,
        "authority": 1.0, "freshness": 1.0, "truth_score": 0.945,
        "claims": {}, "metadata": {},
    }
    events = list(graph.stream(
        {"query": "auth?", "ranked_hits": [hit], "contradictions": [], "memories": []},
        stream_mode=["updates", "custom"],
    ))
    tokens = [chunk["token"] for mode, chunk in events if mode == "custom"]
    updates = [chunk for mode, chunk in events if mode == "updates"]
    answer = updates[-1]["generate"]["answer"]
    assert tokens == ["OAuth ", "2 [github:gh-auth]"]
    assert "### Sources" in answer
    assert "https://demo/gh-auth" in answer


def test_generate_degrades_instead_of_returning_a_sources_only_answer():
    nodes = object.__new__(AgentNodes)
    nodes.chat = SimpleNamespace(stream=lambda _system, _user: iter([]))
    builder = StateGraph(AgentState)
    builder.add_node("generate", nodes.generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    graph = builder.compile()
    hit = {
        "artifact_id": "gh-auth", "source": "github", "title": "Current auth",
        "content": "OAuth 2", "url": "https://demo/gh-auth",
        "updated_at": datetime.now(UTC), "vector_score": 0.9,
        "authority": 1.0, "freshness": 1.0, "truth_score": 0.945,
        "claims": {}, "metadata": {},
    }
    result = graph.invoke({"query": "auth?", "ranked_hits": [hit]})
    assert result["answer"].startswith("The evidence was retrieved")
    assert result["degraded"] == ["answer_generation:ValueError"]
    assert "### Sources" not in result["answer"]
