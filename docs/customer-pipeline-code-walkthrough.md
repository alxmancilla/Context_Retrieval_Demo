# Customer Walkthrough: Source Routing to Reconciliation

This note explains where the demo implements the core MongoDB-backed agentic RAG flow:

1. Source routing
2. Parallel retrieval
3. Reranking
4. Reconciliation

The key customer message is:

> Merge evidence, not answers.


The workflow retrieves and ranks evidence before making one final LLM call. This avoids the slower
pattern where multiple answer-generating subagents each produce full answers and another agent merges
those answers. In this demo, selected source components are thin retrieval tools that return evidence
only.

## End-to-end flow

```text
User question
  → source routing
  → parallel source retrieval tools
  → MongoDB Atlas Search / Vector Search / rank fusion
  → Voyage reranking
  → deterministic reconciliation
  → one final cited answer
```

## 1. Source routing

Source routing is implemented in `agent/nodes.py` in `AgentNodes.parse_intent()`.

It supports three routing modes:

- `intent`: use the model to choose sources.
- `all`: retrieve from all sources for comparison or demos.
- `explicit_only`: route based on explicitly named sources in the user query.

```python
def parse_intent(self, state: AgentState) -> dict:
    query = state["query"]
    if self.source_routing_mode in {"all", "explicit_only"}:
        explicit = self._explicit_sources(query)
        selected = list(ALL_SOURCES) if self.source_routing_mode == "all" else explicit or list(ALL_SOURCES)
        intent = Intent(
            intent="enterprise_knowledge_query", entities={},
            sources=selected, rewritten_query=query,
        )
        return {
            "intent": intent.model_dump(), "selected_sources": intent.sources,
            "source_results": {"__RESET__": []}, "degraded": ["__RESET__"],
        }
```

For normal intent routing, the app asks the configured chat provider to return a typed `Intent` object:

```python
intent = self.chat.invoke_typed(INTENT_SYSTEM, intent_input, Intent)
return {
    "intent": intent.model_dump(), "selected_sources": intent.sources,
    "source_results": {"__RESET__": []}, "degraded": degraded,
}
```

## 2. Parallel retrieval

Parallel fan-out is implemented in `agent/graph.py`.

After routing, LangGraph calls `_dispatch_retrieval()`. It sends one branch to memory retrieval and one branch to each selected source.

```python
def _dispatch_retrieval(state: AgentState) -> list[Send]:
    selected_sources = state.get("selected_sources") or list(ALL_SOURCES)
    shared = {
        "query": state["query"], "intent": state["intent"],
        "realm_id": state["realm_id"], "user_id": state["user_id"],
        "access_principals": state["access_principals"],
    }
    return [
        Send("retrieve_memory", shared),
        *(Send("retrieve_source", {**shared, "source": source})
          for source in selected_sources),
    ]
```

The graph wiring makes retrieval branches converge into reconciliation:

```python
graph.add_conditional_edges(
    "parse_intent", _dispatch_retrieval, ["retrieve_memory", "retrieve_source"]
)
graph.add_edge("retrieve_memory", "reconcile")
graph.add_edge("retrieve_source", "reconcile")
```

Each source retrieval branch calls `AgentNodes.retrieve_source()`:

```python
rows = self.agents[source].search(
    query, state["realm_id"], state["access_principals"]
)
return {"source_results": {source: rows}, "degraded": degraded}
```

The MongoDB retrieval implementation is in `core/source_agents.py`.

The hybrid path uses MongoDB `$rankFusion` over Atlas Vector Search and Atlas Search:

```python
{"$rankFusion": {
    "input": {"pipelines": {
        "semantic": [{"$vectorSearch": {
            "index": SOURCE_VECTOR_INDEX, "path": "content", "query": query,
            "filter": {"$and": self._scope(realm_id, access_principals)},
        }}],
        "lexical": [{"$search": {"index": SOURCE_LEXICAL_INDEX, "compound": {...}}}],
    }},
    "combination": {"weights": {"semantic": 0.7, "lexical": 0.3}},
}}
```

This is the main MongoDB value point: multiple source-specific retrieval tools run parallel,
authorized searches and return evidence before answer generation.

## 3. Reranking

Reranking happens inside `AgentNodes.reconcile()` after all source results are collected and governance is attached.

```python
if self.reranker:
    candidates = [hit for hits in trusted_results.values() for hit in hits]
    reranked = self.reranker.rerank(
        state.get("intent", {}).get("rewritten_query", state["query"]),
        candidates,
    )
    trusted_results = {source: [] for source in trusted_results}
    for hit in reranked:
        trusted_results.setdefault(hit["source"], []).append(hit)
```

If reranking is unavailable, the workflow degrades safely and continues with Atlas scores.

## 4. Reconciliation

Reconciliation starts in `agent/nodes.py` and calls the deterministic scorer in `core/reconciliation.py`.

Before scoring, the app attaches governance policy to retrieved artifacts:

```python
trusted["governance"] = {
    "document_type": policy["document_type"],
    "lifecycle_status": policy["lifecycle_status"],
}
```

Then it calls `reconcile()`:

```python
ranked, conflicts = reconcile(
    trusted_results, registry, weights=self.reconciliation_weights
)
return {"ranked_hits": ranked, "contradictions": conflicts, "degraded": degraded}
```

The scoring formula is in `core/reconciliation.py`:

```python
semantic_score = hit.rerank_score if hit.rerank_score is not None else hit.vector_score
hit.truth_score = round(
    weights.vector * semantic_score
    + weights.authority * hit.authority
    + weights.freshness * hit.freshness,
    6,
)
```

Evidence is sorted by truth score, and contradictions are detected by grouping normalized claims with competing values.

```python
ranked.sort(key=lambda hit: hit.truth_score, reverse=True)
contradictions = detect_contradictions(ranked)
```

## Customer takeaway

This architecture reduces latency and improves governance because it does not ask multiple agents to generate complete answers.

Instead:

- LangGraph routes to source-scoped retrieval tools.
- MongoDB retrieves authorized evidence across selected sources.
- Atlas Search, Vector Search, and `$rankFusion` generate strong candidates.
- Voyage reranking improves semantic ordering when available.
- Deterministic reconciliation combines semantic relevance, authority, and freshness.
- The final model writes once from ranked, governed, cited evidence.

That is the practical meaning of:

> Merge evidence, not answers.
