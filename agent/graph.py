from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.nodes import AgentNodes
from core.schemas import ALL_SOURCES, AgentState


def _dispatch_sources(state: AgentState) -> list[Send]:
    selected_sources = state.get("selected_sources") or list(ALL_SOURCES)
    return [Send("retrieve_source", {
        "source": source, "query": state["query"], "intent": state["intent"],
        "realm_id": state["realm_id"], "user_id": state["user_id"],
        "access_principals": state.get("access_principals", ["public"]),
        "correlation_id": state.get("correlation_id", "unknown"),
    }) for source in selected_sources]


def build_graph(nodes: AgentNodes, checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(AgentState)
    graph.add_node("parse_intent", nodes.parse_intent)
    graph.add_node("retrieve_memory", nodes.retrieve_memory)
    graph.add_node("retrieve_source", nodes.retrieve_source)
    graph.add_node("reconcile", nodes.reconcile)
    graph.add_node("generate", nodes.generate)
    graph.add_node("save_memory", nodes.save_memory)
    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "retrieve_memory")
    graph.add_conditional_edges("retrieve_memory", _dispatch_sources, ["retrieve_source"])
    graph.add_edge("retrieve_source", "reconcile")
    graph.add_edge("reconcile", "generate")
    graph.add_edge("generate", "save_memory")
    graph.add_edge("save_memory", END)
    return graph.compile(checkpointer=checkpointer)
