import re
from collections.abc import Sequence
from typing import Any

CITATION_RE = re.compile(r"\[[a-z]+:[A-Za-z0-9_.:-]+\]")
ROLE_MAP = {
    "human": "user", "humanmessage": "user", "user": "user",
    "ai": "assistant", "aimessage": "assistant", "assistant": "assistant",
    "system": "system", "systemmessage": "system",
    "tool": "tool", "toolmessage": "tool",
}
INCLUDED_ROLES = {"user", "assistant"}


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _message_role(message: Any) -> str:
    raw = str(getattr(message, "type", message.__class__.__name__)).lower()
    return ROLE_MAP.get(raw, raw)


def _truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 20:
        return text[:limit]
    head = max(1, (limit - 15) // 2)
    tail = max(1, limit - head - 15)
    return f"{text[:head]}\n[…truncated…]\n{text[-tail:]}"


def _citations(text: str) -> list[str]:
    return list(dict.fromkeys(CITATION_RE.findall(text)))[:8]


def _context_item(role: str, content: str, index: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"role": role, "content": content}
    if index is not None:
        item["turn_index"] = index
    citations = _citations(content)
    if citations:
        item["citations"] = citations
    return item


def recent_conversation_context(
    messages: Sequence[Any], current_query: str, previous_summary: str = "",
    max_messages: int = 6, max_chars: int = 4000,
) -> list[dict[str, Any]]:
    """Build a bounded, non-authoritative context package from checkpoint messages."""
    candidates = [message for message in messages if _message_role(message) in INCLUDED_ROLES]
    if candidates and _message_role(candidates[-1]) == "user":
        if _message_content(candidates[-1]).strip() == current_query.strip():
            candidates.pop()

    selected: list[dict[str, Any]] = []
    summary_budget = min(len(previous_summary), max(0, max_chars // 4))
    remaining = max_chars - summary_budget
    for offset, message in enumerate(reversed(candidates[-max_messages:])):
        content = _message_content(message).strip()
        if not content or remaining <= 0:
            continue
        content = _truncate_middle(content, remaining)
        selected.append(_context_item(_message_role(message), content, len(candidates) - offset))
        remaining -= len(content)
    selected.reverse()
    if previous_summary and summary_budget > 0:
        summary = _truncate_middle(previous_summary.strip(), summary_budget)
        selected.insert(0, _context_item("summary", summary))
    return selected


def _safe_compaction_cutoff(messages: list[Any], keep_messages: int) -> int:
    cutoff = max(0, len(messages) - keep_messages)
    if 0 < cutoff < len(messages) and _message_role(messages[cutoff]) == "assistant":
        cutoff -= 1
    return cutoff


def compact_conversation(
    messages: Sequence[Any], previous_summary: str = "", keep_messages: int = 6,
    max_summary_chars: int = 1500,
) -> tuple[str, list[str]]:
    """Summarize older turns deterministically and return removable message IDs."""
    eligible_messages = [message for message in messages if _message_role(message) in INCLUDED_ROLES]
    cutoff = _safe_compaction_cutoff(eligible_messages, keep_messages)
    old_messages = eligible_messages[:cutoff]
    if not old_messages:
        return previous_summary, []
    fragments = [previous_summary.strip()] if previous_summary.strip() else []
    fragments.append("Compacted prior turns:")
    fragments.extend(
        _compaction_line(message) for message in old_messages
        if _message_content(message).strip()
    )
    combined = "\n".join(fragments)
    if len(combined) > max_summary_chars:
        combined = _truncate_middle(combined, max_summary_chars)
    removable_ids = [
        str(message.id) for message in old_messages if getattr(message, "id", None)
    ]
    return combined, removable_ids


def _compaction_line(message: Any) -> str:
    role = _message_role(message)
    content = _truncate_middle(_message_content(message).strip().replace("\n", " "), 300)
    citations = _citations(content)
    suffix = f" refs={','.join(citations)}" if citations else ""
    return f"- {role}: {content}{suffix}"