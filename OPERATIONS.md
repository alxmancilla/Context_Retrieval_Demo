# Production Operations

## Readiness and health

- `/health` proves that the Chainlit process is serving HTTP.
- `/ready` initializes the shared runtime, pings MongoDB, verifies all eleven required Atlas
  Search/Vector Search indexes, and returns content-free pool/memory counters plus active
  agent, prompt, and memory-embedding versions.
- Route traffic only when `/ready` returns `200`. Alert after three consecutive failures.

The UI's architecture visual is served as the static asset
`/public/solution-architecture.png` and linked from the Chainlit header/README. If users report
seeing Mermaid source instead of a diagram, confirm they are using the PNG link rather than a raw
Markdown/Mermaid block; Chainlit does not execute Mermaid code blocks in `cl.Text`.

## Local demo lifecycle

The local Chainlit demo is started on demand; documentation and decks do not assume port `8000` is
always running. Start it with `.venv/bin/chainlit run chainlit_app.py --host 127.0.0.1 --port 8000`,
then use `/health`, `/ready`, and `/public/solution-architecture.png` to confirm the UI, runtime,
and refreshed architecture asset are serving. Stop the foreground process with `Ctrl+C`; if the demo
was launched in the background, stop the recorded PID or any listener on port `8000` before starting
a new instance.

## Atlas embedding verification

Do not look for `embedding` or vector array fields in the collections. This demo uses Atlas
Automated Embedding, so vectors are maintained inside managed Atlas Search indexes.

Verify embedding configuration from Atlas **Search Indexes** or metadata-only diagnostics:

- Source collections: `content_vector_acl`, type `vectorSearch`, `autoEmbed` on `content`, model
  `voyage-4`.
- Memory collection: `memory_vector_retained`, type `vectorSearch`, `autoEmbed` on `content`,
  model `voyage-4`.
- Source lexical indexes: `content_lexical`, type `search`, mapped over title/content/artifact ID
  with tenant and principal filters.

The application-side Voyage API key is used for `rerank-3`; Atlas Automated Embedding uses the
Voyage integration configured in Atlas and does not expose embedding credentials to the app.

## Suggested service objectives

Calibrate these values in the target environment before committing to an SLO:

| Signal | Initial objective |
|---|---|
| Readiness | 99.9% successful probes over 30 days |
| Retrieval p95 | Under 2 seconds per source at expected ACL selectivity |
| End-to-end answer p95 | Under 15 seconds |
| Pool checkout failures | Zero during normal load |
| Degraded source branches | Under 1% of turns |
| Verified citation precision | 100% |
| Cross-tenant memory leakage | Zero successful attempts |
| Deleted memory servability | Zero immediately after tombstone acknowledgement |
| Stale durable memory rate | Under 1% of active memories |

Alert on non-READY indexes, pool checkout failures, sustained source degradation, growing
checkpoint/memory collections beyond retention expectations, and evaluation regressions.

Memory counters include write candidates, accepted/rejected decisions, created/reinforced/merged
nodes, deleted-identity suppression, retrieval requests/hits, recent-context characters, and
compacted messages. Recent-context counters reflect user/assistant-only prompt context after
current-query exclusion and bounded truncation. Track acceptance and merge rates over time;
investigate abrupt shifts after prompt, policy, or embedding-profile changes. Counters reset when
the process restarts.

## Capacity validation

Use `python -m scripts.load_retrieval --rounds 20 --workers 10` as a bounded retrieval test.
Increase one dimension at a time while monitoring Atlas connections, query latency, search-node
CPU, disk IOPS, and application pool counters. The script prints metrics only, never content.
Do not infer production capacity from the default five-worker smoke.

## Backup and restore

1. Enable Atlas continuous cloud backup or scheduled snapshots according to the required RPO.
2. Confirm the database and search-index definitions are included in infrastructure inventory.
3. Quarterly, restore a snapshot into an isolated project, run bootstrap in drift-detection mode,
   wait for all indexes, and execute ACL, retention, retrieval, and live RAG evaluations.
4. Record restore duration, data timestamp, index rebuild duration, and validation evidence.
5. Never test restore by overwriting the active demo or production database.

## Tenant deletion

Thread ownership records map tenant/user scope to LangGraph checkpoint IDs. Preview collection
counts through approved operational tooling, then run the destructive command only after change
approval:

`python -m scripts.delete_tenant --realm-id REALM --confirm-realm REALM`

The exact-match confirmation prevents accidental broad deletion. The operation removes source
artifacts, registry/governance/claim records, memories, owned checkpoints, and thread mappings.
Atlas backups retain historical copies until their configured expiry; include that fact in the
tenant deletion contract.

## Schema-validation rollout

Local bootstrap defaults to `moderate`/`warn`. Review Atlas validation warnings and correct old
documents before setting `MONGODB_VALIDATION_ACTION=error`, which applies `strict`/`error`.
Production defaults to `error`. Connector service accounts must not have write access to
`artifact_governance`, `sources`, or `thread_ownership`.
Bootstrap upgrades legacy memories in place to schema v2 before applying the validator and
rebuilds the memory Vector Search definition when governed filter fields drift.

## Incident checklist

1. Preserve correlation IDs, structured degradation markers, Atlas audit records, and provider
   request identifiers; never copy raw prompts or PHI into logs.
2. Check `/ready`, search-index status, pool checkout failures, and Atlas metrics.
3. If lexical Search is unavailable, confirm vector-only degradation is explicit.
4. If a governance policy is missing, treat the artifact as unverified and investigate ingestion.
5. Rotate exposed credentials, restrict access, and follow the provider/PHI process in
   `SECURITY.md`.