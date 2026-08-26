import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from agent.graph import build_graph


class FakeAsyncNodes:
    def validate_access(self, state):
        return {}

    def parse_intent(self, state):
        sources = ["github"] if "github only" in state["query"] else ["github", "jira"]
        return {
            "intent": {"rewritten_query": state["query"]},
            "selected_sources": sources,
            "source_results": {"__RESET__": []},
            "degraded": ["__RESET__"],
        }

    def retrieve_memory(self, state):
        return {"memories": []}

    def retrieve_source(self, state):
        return {"source_results": {state["source"]: [{"source": state["source"]}]}}

    def reconcile(self, state):
        return {"ranked_hits": [], "contradictions": []}

    def generate(self, state):
        return {"answer": "grounded test answer"}

    def save_memory(self, state):
        return {}

    def compact_conversation(self, state):
        return {"conversation_summary": ""}


def test_async_ui_graph_path_and_multi_turn_source_reset():
    async def scenario():
        graph = build_graph(FakeAsyncNodes(), InMemorySaver())
        config = {"configurable": {"thread_id": "ui-test"}}
        seen = []
        initial = {
            "query": "search broadly", "realm_id": "r", "user_id": "u",
            "access_principals": ["role:test"], "correlation_id": "first",
        }
        async for update in graph.astream(initial, config=config, stream_mode="updates"):
            seen.extend(update)
        first = (await graph.aget_state(config)).values
        assert set(first["source_results"]) == {"github", "jira"}
        assert {"validate_access", "parse_intent", "retrieve_memory", "retrieve_source", "reconcile",
                "generate", "save_memory"} <= set(seen)
        assert "compact_conversation" in seen

        second = {**initial, "query": "github only", "correlation_id": "second"}
        async for _ in graph.astream(second, config=config, stream_mode="updates"):
            pass
        final = (await graph.aget_state(config)).values
        assert set(final["source_results"]) == {"github"}
        assert final["answer"] == "grounded test answer"

    asyncio.run(scenario())
