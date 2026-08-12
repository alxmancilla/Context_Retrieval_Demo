from datetime import datetime
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

SourceName = Literal["github", "confluence", "jira", "sharepoint", "teams"]
ALL_SOURCES: tuple[SourceName, ...] = (
    "github", "confluence", "jira", "sharepoint", "teams"
)


class Intent(BaseModel):
    intent: str = Field(description="Short intent label")
    entities: dict[str, str] = Field(default_factory=dict)
    sources: list[SourceName] = Field(
        default_factory=lambda: list(ALL_SOURCES), min_length=1
    )
    rewritten_query: str


class ArtifactGovernance(BaseModel):
    document_type: str = "reference"
    lifecycle_status: str = "active"
    authority_override: float | None = Field(default=None, ge=0.0, le=1.0)


class SourceHit(BaseModel):
    artifact_id: str
    source: SourceName
    title: str
    content: str
    url: str
    updated_at: datetime
    vector_score: float
    rerank_score: float | None = None
    authority: float = 0.0
    freshness: float = 0.0
    truth_score: float = 0.0
    claims: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    governance: ArtifactGovernance = Field(default_factory=ArtifactGovernance)


class ContradictionRepresentative(BaseModel):
    artifact_id: str
    source: SourceName
    truth_score: float
    updated_at: datetime
    lifecycle_status: str
    document_type: str


class Contradiction(BaseModel):
    claim: str
    values: dict[str, list[str]]
    preferred_value: str
    preferred_artifact: str
    representatives: dict[str, ContradictionRepresentative]
    score_margin: float
    reason: str


def merge_source_results(left: dict | None, right: dict | None) -> dict:
    incoming = right or {}
    if "__RESET__" in incoming:
        return {key: value for key, value in incoming.items() if key != "__RESET__"}
    return {**(left or {}), **incoming}


def merge_degraded(left: list[str] | None, right: list[str] | None) -> list[str]:
    reset = "__RESET__"
    incoming = right or []
    base = incoming[incoming.index(reset) + 1:] if reset in incoming else [*(left or []), *incoming]
    return list(dict.fromkeys(item for item in base if item != reset))


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    source: SourceName
    intent: dict[str, Any]
    selected_sources: list[SourceName]
    source_results: Annotated[dict[str, list[dict]], merge_source_results]
    memories: list[dict]
    ranked_hits: list[dict]
    contradictions: list[dict]
    answer: str
    degraded: Annotated[list[str], merge_degraded]
    realm_id: str
    user_id: str
    access_principals: list[str]
    correlation_id: str
