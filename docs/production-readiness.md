# Production Readiness Notes

This document captures the MongoDB and agentic-AI architecture boundaries to discuss before moving
from the demo profile to a production implementation.

## Index inventory

| Area | Collection(s) | Index / control | Purpose |
|---|---|---|---|
| Source semantic retrieval | `github`, `confluence`, `jira`, `sharepoint`, `teams` | `content_vector_acl` | Atlas Vector Search with Automated Embedding on `content` and tenant/ACL filters. |
| Source lexical retrieval | same five source collections | `content_lexical` | Atlas Search over title, content, and artifact identifiers for exact terms and IDs. |
| Hybrid retrieval | same five source collections | `$rankFusion` | Combines semantic and lexical rankings without merging raw scores. |
| Governed memory | `memories` | `memory_vector_retained` | Atlas Vector Search for retained, non-authoritative memory-v2 nodes. |
| Claim comparison | `claim_assertions` | claim/source/tenant lookup indexes | Provides ACL-scoped alternatives for contradiction detection. |
| Governance | `artifact_governance` | artifact/source/tenant lookup indexes | Protected authority, lifecycle, and document-class metadata. |
| Lifecycle | memories/checkpoints | TTL indexes | Enforces memory and checkpoint retention windows. |

Readiness should fail closed when any required Search or Vector Search index is unavailable.

## Production ingestion lifecycle

For real source systems, keep ingestion deterministic and observable:

1. Connector reads source metadata, body text, permissions, update time, and deletion state.
2. Normalizer maps records to the artifact contract and stable `artifact_id` values.
3. ACL mapper writes `realm_id` and `access_principals` before search indexing.
4. Claim extractor writes normalized `claim_assertions` for facts the system can compare.
5. Governance loader writes protected lifecycle, authority, and document-class records.
6. Atlas Search/Vector Search indexes update through the managed index lifecycle.
7. Validation runs schema checks, index readiness, ACL isolation, retrieval evals, and live RAG gates.
8. Deletions write tombstones or remove records according to the source retention policy.

Atlas Automated Embedding simplifies the application path, but production plans should document region
availability, model availability, index rebuild expectations, cost, and a fallback plan for
application-managed embeddings if the managed integration is unavailable in the target environment.

## Failure-mode demo script

Use these scenarios to show that the workflow degrades safely instead of becoming ungrounded:

| Scenario | Expected behavior |
|---|---|
| Reranker unavailable | Atlas scores remain available; degradation is reported; unauthorized documents are still excluded. |
| One source branch unavailable | The branch is marked degraded; remaining retrieved evidence is reconciled; answer stays grounded or safely declines. |
| Routing uncertainty | The workflow falls back to all selected/available sources rather than inventing evidence. |
| Stale source conflicts with effective policy | Protected governance and claim assertions select the current authoritative representative. |
| Unauthorized principal asks for restricted content | Atlas pre-filters return no unauthorized evidence; reranker and writer never see restricted content. |
| Generation failure after retrieval | The system can return a safe degraded response without fabricated citations. |

## Production limits to state explicitly

This demo validates architecture and correctness signals, not every production dimension. Before a
production rollout, measure and harden:

- connector throughput and source API backoff behavior
- high-concurrency Atlas Search and Vector Search latency
- Search index size, rebuild time, and regional availability
- cost per answer across routing, retrieval, reranking, and generation
- real identity-provider group and realm claim mapping
- human approval workflows for write/actions, if actions are added later
- multi-region disaster recovery and restore rehearsals
- calibrated faithfulness or answer-quality judging beyond deterministic metric gates

## Design principle

Do not add autonomous agents to solve governance problems. Keep source adapters thin, preserve
central reconciliation, and treat the final model as a grounded writer rather than the authority
engine, permission boundary, or citation source.