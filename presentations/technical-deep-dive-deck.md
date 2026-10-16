# Technical Deep Dive: Governed Source-Aware RAG

Technical presentation for architects and engineering stakeholders.

---

## 1. Technical objective

Build an enterprise RAG assistant that can:

- retrieve from multiple source-specific collections
- enforce identity, tenant, and ACL filters
- combine vector and lexical retrieval
- rerank candidates with Voyage `rerank-3`
- resolve contradictions with deterministic governance
- generate cited answers
- maintain governed short-term and durable memory

---

## 2. System components

Core components:

- Chainlit UI for the demo experience.
- LangGraph coordinator for stateful workflow orchestration.
- Thin source agents for GitHub, Confluence, Jira, SharePoint, and Teams.
- MongoDB Atlas for source data, governance records, claims, checkpoints, and memory.
- Atlas Vector Search and Atlas Search for retrieval.
- Voyage `rerank-3` for global candidate reranking.
- Azure Grove model endpoint for answer generation.

---

## 3. High-level architecture

![Solution architecture](../public/solution-architecture.png)

Key idea: generation is only the final step. Retrieval, filtering, ranking, governance, and citation binding happen before the answer is presented.

---

## 4. Source-aware retrieval model

Each source collection represents a different enterprise system.

The demo keeps source-specific context such as:

- source name
- source URL
- tenant realm
- ACL principals
- artifact metadata
- timestamps
- lifecycle information
- claim values

This keeps source identity available through retrieval, reconciliation, and citations.

---

## 5. Atlas index strategy

The demo uses 11 search/vector indexes:

- 5 source vector indexes named `content_vector_acl`.
- 5 source lexical indexes named `content_lexical`.
- 1 retained memory vector index named `memory_vector_retained`.

The source vector indexes use Atlas Automated Embedding with Voyage `voyage-4` over the `content` path.

---

## 6. Hybrid retrieval path

For each selected source:

1. Apply tenant and ACL filters.
2. Run semantic retrieval through Atlas Vector Search.
3. Run lexical retrieval through Atlas Search.
4. Combine both rankings with MongoDB `$rankFusion`.
5. Return only authorized candidates.

`$rankFusion` is used because vector and lexical scores are not naturally comparable.

---

## 7. Global reranking

After source retrieval:

- Candidates from all sources are pooled.
- Voyage `rerank-3` scores candidates against the rewritten query.
- Rerank scores are mapped back to the original Atlas documents.
- `top_k=None` preserves evidence for contradiction analysis.
- Atlas similarity remains a fallback if reranking is unavailable.

Reranking improves candidate ordering but does not replace governance.

---

## 8. Deterministic reconciliation

The reconciliation layer combines:

- semantic or rerank relevance
- source authority
- freshness
- governance metadata
- lifecycle state
- contradiction representatives

Default truth-score weighting:

- 55% semantic relevance
- 30% source authority
- 15% freshness

Weights are configurable and validated.

---

## 9. Governance and claim boundaries

Runtime truth metadata comes from protected governance records, not from untrusted generated text.

The demo maintains:

- `artifact_governance` records for protected source truth.
- `claim_assertions` for normalized, ACL-scoped claims.
- contradiction representatives for alternate claim values.
- current and historical claim status.

This allows the system to explain why one source wins over another.

---

## 10. Citation integrity

The answer pipeline binds citations to retrieved evidence.

Important behavior:

- generated source placeholders are rebound to verified evidence
- known citation links are stripped and replaced with retrieved URLs
- cited evidence remains inspectable in the UI
- production streaming can be buffered to protect citation integrity

The goal is to avoid unsupported or fabricated citations.

---

## 11. Identity and access control

The graph fails closed when required identity context is missing.

Retrieval uses:

- realm filtering
- tenant ownership checks
- principal-based ACL filtering
- production OAuth configuration checks

Unauthorized content is filtered before reranking and generation, reducing risk that the LLM sees content the user cannot access.

---

## 12. Memory-v2 design

Memory-v2 separates durable user memory from normal enterprise Q&A.

It supports:

- selective writes
- semantic merge and reinforcement
- deleted-memory suppression
- TTL retention
- schema and model versioning
- memory observability counters

Rejected examples include normal Q&A, degraded turns, and content that should not become durable user state.

---

## 13. Short-term conversation context

The demo also manages recent-turn context.

Safeguards include:

- user and assistant message filtering
- role normalization
- multimodal text flattening
- current-query exclusion
- citation metadata preservation
- turn-boundary-safe compaction

Short-term context improves follow-up behavior without becoming authoritative knowledge.

---

## 14. Readiness and operational controls

Readiness includes checks for:

- MongoDB connectivity
- all configured search/vector indexes
- memory version metadata
- schema and retention invariants
- connection pool telemetry

The demo also includes scripts for schema checks, ACL checks, retention checks, tenant deletion, load smoke testing, and UI smoke testing.

---

## 15. Validation model

Validation covers multiple layers:

- offline unit tests
- schema/index diagnostics
- live integration tests
- retrieval assurance evaluations
- Chainlit graph-path smoke test
- load smoke checks
- documentation and configuration checks

Current known follow-up: deterministic live RAG gates need investigation for one latency-budget miss and one required-term coverage miss.

---

## 16. Production design principles

The implementation demonstrates these production patterns:

- fail closed on missing identity
- filter before reranking and generation
- keep governance metadata protected
- treat LLM output as non-authoritative
- bind citations to retrieved evidence
- make memory selective and observable
- expose readiness and degradation markers

---

## 17. Recommended technical demo path

1. Show the architecture diagram.
2. Walk through source retrieval and ACL filtering.
3. Explain `$rankFusion` and reranking.
4. Demonstrate a contradiction query.
5. Inspect evidence, truth scores, and citations.
6. Explain memory-v2 write decisions.
7. Close with readiness and operational checks.

---

## 18. Closing architecture takeaway

The demo is not only a chatbot.

It is a reference pattern for governed enterprise RAG:

**authorized retrieval → hybrid fusion → reranking → deterministic governance → cited generation → governed memory**
