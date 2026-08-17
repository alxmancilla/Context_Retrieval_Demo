import asyncio
import atexit
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.mongodb import MongoDBSaver

from agent.graph import build_graph
from agent.nodes import AgentNodes
from core.observability import configure_logging, get_logger, log_failure
from core.providers.chat import GroveChatProvider
from core.providers.rerank import create_voyage_reranker
from core.security import credentials_match, resolve_access_context
from core.settings import Settings, configured_auth_mode, get_settings
from db.bootstrap import connect
from ui.presentation import (
    contradictions_markdown,
    evidence_markdown,
    intent_markdown,
    memories_markdown,
    source_result_markdown,
)

LOGGER = get_logger("chainlit")


@dataclass(frozen=True)
class AppRuntime:
    client: Any
    graph: Any
    settings: Settings


_RUNTIME: AppRuntime | None = None
_RUNTIME_LOCK = asyncio.Lock()


STARTER_PROMPTS = (
    ("Rx partner authentication", "How do external partners authenticate to the Rx API today, and are any sources outdated?"),
    ("Prior auth status delivery", "For prior auth, should clients poll for status or consume events? What changed and when?"),
    ("Eligibility cache strategy", "What is the current eligibility caching strategy? Include TTL values and the incident that drove the change."),
    ("PHI logging policy", "What is the documented PHI logging policy, and how does it differ from old troubleshooting practices?"),
    ("Partner network controls", "What Atlas network and transport controls are required for production Rx partner connectivity, and which evidence verifies them?"),
    ("PA event resilience", "How does prior authorization event delivery handle idempotency, stream lag, failures, and dead-letter processing?"),
    ("Negative cache TTL", "What are the positive and negative eligibility cache TTLs, and why are they different?"),
    ("PHI-safe troubleshooting", "How should engineers troubleshoot a PHI-related production incident without logging raw payloads?"),
    ("Resolve the OAuth conflict", "Compare OAuth claims in GitHub, Jira, Confluence, and Teams. Which claim wins under authority and freshness, and why?"),
    ("Trace the cache decision", "Build a timeline from the 60-minute eligibility cache design to the current deployment. Cite the incident, ticket, and implementation."),
    ("Audit the PA migration", "Summarize evidence that tier-1 prior authorization consumers migrated from polling to events and identify any remaining exceptions."),
    ("Enterprise control coverage", "Across Partner Integration Gateway, Member API, and Provider API, summarize current authentication controls using implementation, architecture, rollout, and compliance evidence."),
)


if configured_auth_mode() == "password":
    @cl.password_auth_callback
    async def authenticate(username: str, password: str):
        settings = get_settings()
        if not credentials_match(settings, username, password):
            return None
        return cl.User(
            identifier=username,
            metadata={
                "realm_id": settings.realm_id,
                "user_id": username,
                "principals": list(settings.access_principals),
            },
        )


@cl.set_starters
async def starters(_user: cl.User | None) -> list[cl.Starter]:
    return [cl.Starter(label=label, message=message) for label, message in STARTER_PROMPTS]


def _build_runtime(settings: Settings) -> AppRuntime:
    configure_logging(settings.log_level)
    client, db = connect(
        settings.mongodb_uri,
        settings.mongodb_db,
        server_selection_timeout_ms=settings.mongodb_server_selection_timeout_ms,
        connect_timeout_ms=settings.mongodb_connect_timeout_ms,
        socket_timeout_ms=settings.mongodb_socket_timeout_ms,
    )
    try:
        chat = GroveChatProvider(
            api_key=settings.grove_api_key,
            base_url=settings.grove_base_url,
            model=settings.grove_model,
            timeout_seconds=settings.grove_timeout_seconds,
            max_retries=settings.grove_max_retries,
        )
        nodes = AgentNodes(
            db, chat, settings.source_top_k, settings.memory_top_k,
            settings.memory_retention_days, settings.memory_max_per_user,
            reconciliation_weights=settings.reconciliation_weights,
            reranker=create_voyage_reranker(
                api_key=settings.voyage_api_key,
                model=settings.voyage_rerank_model,
                timeout_seconds=settings.voyage_rerank_timeout_seconds,
                max_retries=settings.voyage_rerank_max_retries,
            ),
        )
        graph = build_graph(nodes, MongoDBSaver(
            client, db_name=settings.mongodb_db,
            ttl=settings.checkpoint_retention_days * 86400,
        ))
        return AppRuntime(client=client, graph=graph, settings=settings)
    except Exception:
        client.close()
        raise


async def _get_runtime() -> AppRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        async with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = await cl.make_async(_build_runtime)(get_settings())
    return _RUNTIME


def _close_runtime() -> None:
    if _RUNTIME is not None:
        _RUNTIME.client.close()


atexit.register(_close_runtime)


def should_stream_draft(app_env: str) -> bool:
    return app_env != "production"


async def _initialize_session() -> None:
    runtime = await _get_runtime()
    settings = runtime.settings
    user = cl.user_session.get("user")
    access = resolve_access_context(
        settings,
        identifier=getattr(user, "identifier", None),
        metadata=getattr(user, "metadata", None),
    )
    cl.user_session.set("graph", runtime.graph)
    cl.user_session.set("thread_id", str(uuid4()))
    cl.user_session.set("settings", settings)
    cl.user_session.set("access_context", access)


@cl.on_chat_start
async def on_chat_start() -> None:
    try:
        await _initialize_session()
    except Exception as exc:
        log_failure(
            LOGGER, "session_initialization_failed", exc,
            correlation_id=None, node="session_init",
        )
        await cl.Message(
            content="Unable to initialize Atlas or Grove. Check the local configuration and restart."
        ).send()


async def _show_update(node: str, payload: dict) -> None:
    if node == "parse_intent":
        async with cl.Step(name="Coordinator · intent and routing", type="llm") as step:
            step.output = intent_markdown(payload.get("intent", {}))
    elif node == "retrieve_memory":
        async with cl.Step(name="MongoDB · semantic memory", type="retrieval") as step:
            step.output = f"Retrieved {len(payload.get('memories', []))} relevant memories."
    elif node == "retrieve_source":
        for source, hits in payload.get("source_results", {}).items():
            async with cl.Step(name=f"Source agent · {source.title()}", type="retrieval") as step:
                step.output = source_result_markdown(source, hits)
    elif node == "reconcile":
        async with cl.Step(name="Coordinator · truthiness reconciliation", type="rerank") as step:
            step.output = (
                f"Ranked {len(payload.get('ranked_hits', []))} artifacts and found "
                f"{len(payload.get('contradictions', []))} contradictions."
            )
    elif node == "save_memory":
        async with cl.Step(name="MongoDB · persist memory", type="tool") as step:
            step.output = "Turn checkpoint and semantic memory saved."


@cl.on_message
async def on_message(message: cl.Message) -> None:
    graph = cl.user_session.get("graph")
    settings = cl.user_session.get("settings")
    access = cl.user_session.get("access_context")
    thread_id = cl.user_session.get("thread_id")
    if not graph or not settings or not access or not thread_id:
        await cl.Message(content="The session is unavailable. Start a new chat and try again.").send()
        return

    status = cl.Message(content="Analyzing intent and routing enterprise sources…")
    await status.send()
    config = {"configurable": {"thread_id": thread_id}}
    correlation_id = str(uuid4())
    graph_input = {
        "query": message.content,
        "messages": [HumanMessage(content=message.content)],
        "realm_id": access.realm_id,
        "user_id": access.user_id,
        "access_principals": list(access.principals),
        "correlation_id": correlation_id,
    }
    try:
        first_token = True
        show_draft_tokens = should_stream_draft(settings.app_env)
        async for mode, chunk in graph.astream(
            graph_input, config=config, stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                if chunk.get("event") != "answer_token":
                    continue
                if not show_draft_tokens:
                    continue
                if first_token:
                    status.content = "Draft answer — citations are verified when complete.\n\n"
                    await status.update()
                    first_token = False
                await status.stream_token(chunk["token"])
                continue
            for node, payload in chunk.items():
                if isinstance(payload, dict):
                    await _show_update(node, payload)
        snapshot = await graph.aget_state(config)
        result = snapshot.values
        elements = [
            cl.Text(name="Evidence scores", content=evidence_markdown(result.get("ranked_hits", [])), display="side"),
            cl.Text(name="Contradictions", content=contradictions_markdown(result.get("contradictions", [])), display="side"),
            cl.Text(name="Semantic memory", content=memories_markdown(result.get("memories", [])), display="side"),
        ]
        warning = ""
        if result.get("degraded"):
            warning = f"\n\n> ⚠️ Degraded capabilities: {', '.join(result['degraded'])}"
        status.content = result.get("answer", "No answer was generated.") + warning
        # Chainlit models this field with an unbound ElementBased type variable.
        status.elements = cast(Any, elements)
        await status.update()
    except Exception as exc:
        log_failure(
            LOGGER, "request_failed", exc,
            correlation_id=correlation_id, node="chainlit_request",
        )
        status.content = (
            "The request could not be completed. No ungrounded answer was generated; "
            "check the server logs and try again."
        )
        await status.update()
