# AI Context Platform Assistant — MongoDB Demo

A source-aware, multi-agent RAG demo that simulates GitHub, Confluence, Jira,
SharePoint, and Teams using MongoDB Atlas collections. A LangGraph coordinator
fans out to thin source specialists, then centrally reconciles authority,
freshness, and explicit contradictions before asking Azure Grove for a grounded,
cited answer.

## Key design choices

- One MongoDB collection per simulated enterprise island.
- In-process, MCP-shaped source tools in Phase 1; their descriptors live in the
  `sources` registry so a real MCP transport can replace them later.
- Atlas Automated Embedding indexes use Voyage `voyage-4`. Documents contain
  business data and metadata; vectors are generated and managed inside Atlas Search indexes,
  so source documents do **not** expose an `embedding` array field.
- Each source combines ACL-filtered semantic and lexical retrieval with MongoDB
  `$rankFusion`, improving recall for both concepts and exact identifiers.
- Voyage `rerank-2.5` globally reranks ACL-filtered candidates before deterministic
  reconciliation. Atlas vector similarity remains the fallback if reranking is unavailable.
- Source truth score defaults to 55% semantic relevance, 30% authority, and 15%
  freshness. The three validated `RECONCILIATION_*_WEIGHT` settings support calibrated
  profiles and must sum to `1.0`.
- Contradictions are detected from ACL-scoped records in the indexed `claim_assertions` collection.
- Protected artifact governance distinguishes policy, implementation, runbook, and historical incident
  evidence; contradiction decisions include representatives, lifecycle status, and score margin.
- MongoDB stores LangGraph checkpoints plus auto-embedded, user-scoped semantic
  memory. A deterministic write gate retains only explicit user preferences, decisions, and
  task context; ordinary enterprise Q&A is not promoted to durable memory.
- Recent checkpoint turns and governed durable memory are retrieved in parallel. Older messages
  are compacted into a bounded summary, and neither context source outranks enterprise evidence.
  Recent context is role-normalized, user/assistant-only, citation-preserving, and avoids splitting
  user/assistant turn boundaries during compaction.
- All persisted and retrieved records are scoped by `realm_id`; memory also uses
  `user_id`.

## Architecture

`validated identity → intent parser → parallel recent/durable context + hybrid source agents →
Voyage reranking → deterministic reconciliation → Grove grounded writer → selective memory → compaction`

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the complete component diagram, retrieval
sequence, MongoDB/Voyage rationale, resilience paths, and validation status.
See [`SECURITY.md`](SECURITY.md) for provider data flows and production release gates.
See [`OPERATIONS.md`](OPERATIONS.md) for readiness, SLO, restore, deletion, and incident procedures.

## Contradiction behavior

- Indexed claim assertions group artifacts that make competing assertions about the same fact.
- Reconciliation preserves every supporting artifact ID for audit but selects one scored
  representative for each competing value.
- Representatives include document type, lifecycle status, update timestamp, and truth score.
- Artifact authority overrides let an effective policy outrank an implementation record while
  retaining source-level authority as the default.
- The cross-value score margin makes the strength of the deterministic decision explicit.
- Grove always receives each representative, including low-ranked historical evidence, so it
  can distinguish an old incident suggestion from an approved policy or established practice.
- The Sources appendix is limited to cited, preferred, and representative artifacts instead of
  listing every corroborating document.

## Prerequisites

- Python 3.11+ (the local environment uses Python 3.13).
- MongoDB Atlas 8.0+ with Search, Vector Search, `$rankFusion`, and Automated Embedding
  available (the validated demo cluster runs MongoDB 8.3).
- Voyage indexing and query keys configured for Automated Embedding in Atlas.
  They are configured in Atlas, not passed through this application's CLI.
- A separate application-side Voyage API key for `rerank-2.5`. Set `VOYAGE_API_KEY`;
  Atlas does not expose its Automated Embedding credentials to the application.
- An Azure Grove API key for `gpt-5.6-sol`.

Automated Embedding is currently an Atlas Public Preview capability. Ensure the
cluster region supports it before bootstrapping.

## Environment and dependencies

`pyproject.toml` defines direct runtime dependencies and a separate development group;
`uv.lock` pins the complete environment. Reproduce it with
`uv sync --frozen --group dev`. The legacy `requirements.txt` freeze remains available
for pip environments and matches every overlapping locked version. Ruff, mypy, and
pytest configuration lives in `pyproject.toml` and the tools are pinned in the development
dependency group.

Run the local quality gates with `uv run ruff check .` and `uv run pytest -q`. Validate
the supported Python floor with `uv run --isolated --python 3.11 --frozen --group dev
mypy agent core data db evals scripts ui app.py chainlit_app.py`.

## Setup

1. Copy `.env.example` to `.env` and fill in `MONGODB_URI`, `GROVE_API_KEY`, and
   `VOYAGE_API_KEY`.
2. Install with `uv sync --frozen --group dev`, or use
   `.venv/bin/python -m pip install -r requirements.txt` for the legacy pip workflow.
3. Seed 800 artifacts, protected governance and claim records, validators, five lexical indexes,
   five Automated Embedding indexes, and one memory index:
   `.venv/bin/python app.py bootstrap --wait`
4. Ask a contradiction-rich demo question:
   `.venv/bin/python app.py ask "How does the Rx API authenticate partners, and is any source stale?"`

## Chatbot UI

Start the Chainlit interface with:

`.venv/bin/chainlit run chainlit_app.py --host 127.0.0.1 --port 8000`

Open `http://127.0.0.1:8000`. Each chat receives a MongoDB-checkpointed thread and
shows coordinator routing, parallel source-agent retrieval, truthiness scoring,
contradictions, citations, degraded capabilities, and semantic memory in expandable
steps and side-panel inspectors. In local mode, Grove tokens stream through LangGraph's custom
event channel under an explicit unverified-draft label; production buffers them until the
application binds verified source links to the completed answer.

The UI includes an explicit **Architecture** header link and a README/welcome preview that open
`/public/solution-architecture.png`. The architecture diagram is intentionally not attached as an
automatic side tab on every chat; users open it only when they want the visual design reference.
Use `/health` for process liveness and `/ready` for MongoDB/index readiness, content-free
connection-pool and memory counters, and active agent/prompt/embedding version identifiers.

## Embeddings and reranking

This demo uses embeddings through **Atlas Automated Embedding**, not through visible vector fields
stored in the documents. The embedded text path is `content`.

| Collection(s) | Vector Search index | Embedded path | Model | Visible vector field? |
|---|---|---|---|---|
| `github`, `confluence`, `jira`, `sharepoint`, `teams` | `content_vector_acl` | `content` | `voyage-4` | No |
| `memories` | `memory_vector_retained` | `content` | `voyage-4` | No |

The five source collections also have lexical Atlas Search indexes named `content_lexical` for
exact terms, IDs, titles, and artifact identifiers. Source retrieval runs semantic Vector Search
and lexical Search with tenant/ACL filters, then combines them with `$rankFusion`. Voyage
`rerank-2.5` reranks only the already-authorized candidates returned by Atlas. The final governing
answer is then selected by deterministic reconciliation, not by the embedding or reranker model.

The default connection timeouts are tuned for this low-concurrency demo: Atlas server
selection fails after 5 seconds, connection establishment after 10 seconds, and an
in-flight operation after 60 seconds. Override the corresponding `MONGODB_*_TIMEOUT_MS`
variables after measuring production network and query latency.

Run `.venv/bin/python -m scripts.smoke_ui` to exercise the same asynchronous
LangGraph, Atlas, Grove, checkpoint, and memory path used by the UI.

### Prompt evaluation catalog

**Current-state and contradiction tests**

- `How do external partners authenticate to the Rx API today, and are any sources outdated?`
- `Compare OAuth claims in GitHub, Jira, Confluence, and Teams. Which claim wins under authority and freshness, and why?`
- `For prior auth, should clients poll for status or consume events? What changed and when?`
- `What is the documented PHI logging policy, and how does it differ from old troubleshooting practices?`

**Architecture and operations tests**

- `What Atlas network and transport controls are required for production Rx partner connectivity, and which evidence verifies them?`
- `How does prior authorization event delivery handle idempotency, stream lag, failures, and dead-letter processing?`
- `What are the positive and negative eligibility cache TTLs, and why are they different?`
- `How should engineers troubleshoot a PHI-related production incident without logging raw payloads?`

**Evidence and timeline tests**

- `Build a timeline from the 60-minute eligibility cache design to the current deployment. Cite the incident, ticket, and implementation.`
- `Summarize evidence that tier-1 prior authorization consumers migrated from polling to events and identify any remaining exceptions.`
- `Which artifacts prove that OAuth 1.0 support was removed, and which stale artifacts still claim it is required?`
- `Separate policy, architecture, implementation, rollout, and incident evidence for PHI-safe logging.`

**Enterprise portfolio tests**

- `Across Partner Integration Gateway, Member API, and Provider API, summarize current authentication controls using implementation, architecture, rollout, and compliance evidence.`
- `Which applications have rollout and operational evidence for event-driven prior authorization status delivery?`
- `Compare eligibility cache controls for Member Portal, Benefits Engine, and Pharmacy Transaction Hub.`
- `Create an executive risk brief covering Rx authentication, prior auth delivery, eligibility caching, and PHI logging. Surface stale or contradictory guidance.`

**Multi-turn context test**

1. Ask `How do external partners authenticate to the Rx API today?`
2. Follow with `Which source in your previous answer was stale, and why did it lose?`
3. Then ask `Apply the same authority and freshness reasoning to the eligibility cache decision.`

Follow-ups use bounded checkpoint context, not durable memory. The context pack excludes tool and
system payloads, removes the current query from prior context, preserves prior citation labels such
as `[jira:PA-44]`, and truncates long turns from the middle so both the setup and citations survive.

The corpus contains 200 artifacts for each scenario and 160 artifacts in each of
GitHub, Confluence, Jira, Teams, and SharePoint. The latest 160-record assurance expansion
adds policy, architecture, implementation, validation, runbook, compliance, deprecation,
and operations evidence. All records include stable fake source URLs, realistic source
metadata, governance, official MongoDB documentation references, linked records, and
deliberately stale claims. Expected winners are the current GitHub implementations for Rx
OAuth 2.0 + PKCE, PA event delivery, and the five-minute eligibility TTL; the effective
SharePoint policy governs PHI log redaction.

## Data and source routing

The seed operation is idempotent: artifacts and registry rows are upserted by
realm and stable identifier. Synthetic links intentionally use `demo.cmm.local`
to make clear that the source systems are simulated. Production connectors or
MCP servers can write the same normalized envelope without changing downstream
reconciliation.

## Repository hygiene

Initialize local version control with `git init --initial-branch=main`. Keep `.env`,
virtual environments, caches, logs, private keys, exported credentials, and build
outputs outside source control; the included `.gitignore` covers these paths. Before
the first commit, run `git status --short --ignored` and confirm that `.env` is ignored
while `.env.example` remains visible. Never commit or paste values from `.env`.

## Tests

Run `.venv/bin/python -m pytest`. Unit tests use in-memory fakes and require no
Atlas, Voyage, or Grove credentials. External integration tests are skipped normally.

To verify Atlas index readiness, ACL and retention filters, Voyage reranking, Grove typed
and streaming response shapes, and Chainlit startup on an ephemeral port, run
`RUN_LIVE_INTEGRATION=1 .venv/bin/python -m pytest tests/integration -q`.
The live profile reads credentials from `.env`, never command-line arguments, and does
not print model responses, document content, or secrets.

Run the deterministic RAG evaluation baseline with `.venv/bin/python -m evals.runner`.
It records metric-only results under ignored `evals/results/`: expected claim winner,
representative selection, required-term coverage, verified citation precision, concise-source
limits, stale-evidence identification, latency budget, and safe degradation. The exact PHI
policy case requires the effective SharePoint policy to win, the historical Teams suggestion
to remain grounded, and no more than six appendix artifacts. This is a transparent regression
proxy, not a substitute for expert review or a calibrated faithfulness judge.

Run `.venv/bin/python -m evals.retrieval_runner` for four additional assurance-control
retrieval checks covering JWKS rotation, PA dead-letter replay, eligibility invalidation, and
break-glass PHI logging. Run `.venv/bin/python -m scripts.load_retrieval --rounds 3 --workers 5`
for a bounded, metric-only concurrent Atlas retrieval smoke; it prints no document content.

Current validated baseline: **114 unit/default-profile tests pass**, four credential-gated live
tests skip by default, **4/4 live RAG cases pass**, and **4/4 assurance retrieval cases pass**.

## Security note

This is a demo. Production requires source-level authorization propagation,
permission-aware retrieval, audit retention, secret management, PII controls,
and evaluation gates. Never commit `.env`; do not introduce real PHI until every gate in
[`SECURITY.md`](SECURITY.md) is satisfied.

Source retrieval now enforces both `realm_id` and an indexed intersection with each
artifact's `access_principals`. Local mode uses `ACCESS_PRINCIPALS`; set
`AUTH_MODE=password`, `AUTH_USERNAME`, `AUTH_PASSWORD`, and a strong
`CHAINLIT_AUTH_SECRET` to enable Chainlit's local password callback. Password mode is
for controlled demonstrations only. Production requires `AUTH_MODE=oauth`, an
`OAUTH_ALLOWED_PROVIDERS` allowlist, and validated realm/group claim mappings.

Chainlit defaults to localhost-only origins, disabled uploads, a 30-minute connection
session, and 24-hour user-session expiry. `APP_ENV=production` refuses non-OAuth auth,
buffers unverified draft tokens, and requires HTTPS for Grove.
Password-mode signing secrets must be non-placeholder values of at least 32 characters.
For deployment, replace the localhost origins with the
exact HTTPS application origin and integrate enterprise OAuth/OIDC before exposure.

Application degradation is emitted as structured JSON with event, correlation ID,
graph node, source, exception type, and degraded capability. Prompts, retrieved content,
credentials, and raw exception text are excluded. Configure `LOG_LEVEL`,
`GROVE_TIMEOUT_SECONDS`, `GROVE_MAX_RETRIES`, `VOYAGE_RERANK_TIMEOUT_SECONDS`, and
`VOYAGE_RERANK_MAX_RETRIES` for the deployment environment.

Durable memories are selectively written, redacted, typed, importance-scored, semantically
merged or reinforced, versioned, provenance-tagged, capped per user, and filtered by tenant,
user, type, validity, tombstone, and expiry. Deletion immediately suppresses and redacts both
content and summary; TTL later removes the document. Chainlit reuses one process-level MongoDB
client instead of creating a connection pool per chat session.
Pool size and wait-queue limits are configurable, and `/ready` exposes only counters.
LangGraph checkpoints use `CHECKPOINT_RETENTION_DAYS`. To exercise the confirmed
deletion path, run `.venv/bin/python app.py forget --confirm`; use `--user-id` only as
an authorized realm administrator.
