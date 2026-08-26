import re
from dataclasses import dataclass
from typing import Literal

MemoryType = Literal["user_preference", "user_decision", "task_context", "legacy_context"]
MEMORY_TYPES: tuple[MemoryType, ...] = (
    "user_preference", "user_decision", "task_context", "legacy_context",
)
MEMORY_SCHEMA_VERSION = 2

_PREFERENCE = re.compile(
    r"\b(i prefer|my preference|please call me|call me|i like responses|"
    r"please use|do not show me|don't show me)\b", re.IGNORECASE,
)
_DECISION = re.compile(
    r"\b(i decided|we decided|our decision|decision is|i have decided)\b", re.IGNORECASE,
)
_TASK_CONTEXT = re.compile(
    r"\b(remember that i|remember my|i am working on|i'm working on|"
    r"my current project|my goal|for next time|follow up with me)\b", re.IGNORECASE,
)
_UNSAFE_ANSWERS = (
    "I don't have enough retrieved enterprise context",
    "The evidence was retrieved, but answer generation is temporarily unavailable",
)


@dataclass(frozen=True)
class MemoryWriteDecision:
    accepted: bool
    reason: str
    memory_type: MemoryType | None = None
    importance: float = 0.0
    content: str = ""
    summary: str = ""


def decide_memory_write(
    query: str, answer: str, degraded: list[str], min_importance: float = 0.65,
) -> MemoryWriteDecision:
    """Select only explicit user-specific continuity; enterprise facts stay in source data."""
    if degraded:
        return MemoryWriteDecision(False, "turn_degraded")
    if not answer.strip() or answer.startswith(_UNSAFE_ANSWERS):
        return MemoryWriteDecision(False, "answer_unavailable")

    match: tuple[MemoryType, float, str] | None = None
    if _PREFERENCE.search(query):
        match = ("user_preference", 0.85, "explicit_user_preference")
    elif _DECISION.search(query):
        match = ("user_decision", 0.90, "explicit_user_decision")
    elif _TASK_CONTEXT.search(query):
        match = ("task_context", 0.75, "explicit_task_context")
    if match is None:
        return MemoryWriteDecision(False, "enterprise_qa_not_durable")

    memory_type, importance, reason = match
    if importance < min_importance:
        return MemoryWriteDecision(False, "below_importance_threshold")
    content = query.strip()[:2500]
    return MemoryWriteDecision(
        True, reason, memory_type, importance, content, content[:500],
    )