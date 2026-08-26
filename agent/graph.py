from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.nodes import AgentNodes
from core.schemas import ALL_SOURCES, AgentState


def _dispatch_retrieval(state: AgentState) -> list[Send]:
    selected_sources = state.get("selected_sources") or list(ALL_SOURCES)
    shared = {
        "query": state["query"], "intent": state["intent"],
        "realm_id": state["realm_id"], "user_id": state["user_id"],
        "access_principals": state["access_principals"],
        "correlation_id": state.get("correlation_id", "unknown"),
        "messages": state.get("messages", []),
        "conversation_summary": state.get("conversation_summary", ""),
    }
    return [
        Send("retrieve_memory", shared),
        *(Send("retrieve_source", {**shared, "source": source})
          for source in selected_sources),
    ]


def build_graph(nodes: AgentNodes, checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(AgentState)
    graph.add_node("validate_access", nodes.validate_access)
    graph.add_node("parse_intent", nodes.parse_intent)
    graph.add_node("retrieve_memory", nodes.retrieve_memory)
    graph.add_node("retrieve_source", nodes.retrieve_source)
    graph.add_node("reconcile", nodes.reconcile)
    graph.add_node("generate", nodes.generate)
    graph.add_node("save_memory", nodes.save_memory)
    graph.add_node("compact_conversation", nodes.compact_conversation)
    graph.add_edge(START, "validate_access")
    graph.add_edge("validate_access", "parse_intent")
    graph.add_conditional_edges(
        "parse_intent", _dispatch_retrieval, ["retrieve_memory", "retrieve_source"]
    )
    graph.add_edge("retrieve_memory", "reconcile")
    graph.add_edge("retrieve_source", "reconcile")
    graph.add_edge("reconcile", "generate")
    graph.add_edge("generate", "save_memory")
    graph.add_edge("save_memory", "compact_conversation")
    graph.add_edge("compact_conversation", END)
    return graph.compile(checkpointer=checkpointer)
