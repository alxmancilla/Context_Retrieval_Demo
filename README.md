# AI Context Platform Assistant — MongoDB Demo

This demo shows how MongoDB Atlas can be the shared retrieval, governance, and state layer for an
agentic RAG workflow.

The customer scenario is a healthcare enterprise assistant that answers questions across simulated
GitHub, Confluence, Jira, SharePoint, and Teams content. The workflow retrieves evidence from the
right sources, reconciles conflicts deterministically, and then asks one model to write one cited
answer.

The core message is:

> **Merge evidence, not answers.**

Instead of asking multiple answer-writing subagents to each generate prose and then calling another
agent to merge those answers, this demo retrieves source evidence in parallel, ranks and reconciles it
centrally, and generates once from governed, cited context.

In this repository, the coordinator calls thin source-scoped retrieval tools, not independent
answer-generating subagents. Each tool returns MongoDB evidence only; the final answer is written once
after reranking and reconciliation.

## Use case

Many enterprise RAG implementations become slow when a main agent calls several answer-writing
subagents and then waits for a separate merge step. The individual subagent answers may be good, but
the final synthesis adds latency and can make citations, authority, and stale-source handling harder
to explain.

This demo shows a better pattern:

1. Route the question to relevant enterprise sources.
2. Retrieve authorized evidence from selected sources in parallel.
3. Use MongoDB Atlas Search, Vector Search, and `$rankFusion` to produce strong candidates.
4. Rerank authorized candidates with Voyage `rerank-3`.
5. Reconcile evidence using source authority, freshness, lifecycle status, and normalized claims.
6. Generate one final cited answer.

The healthcare profile includes questions about Rx API authentication, prior authorization event
delivery, eligibility-cache TTLs, and PHI-safe troubleshooting. The same architecture can be reused
for other customer profiles by changing source artifacts, authority rules, prompts, and evaluations.

## MongoDB value proposition

MongoDB Atlas is used as the operational context plane for the assistant:

| Capability | MongoDB value in this demo |
|---|---|
| Multi-source evidence | Five Atlas collections simulate GitHub, Confluence, Jira, SharePoint, and Teams. |
| Hybrid retrieval | Atlas Vector Search and Atlas Search are fused with `$rankFusion`. |
| Managed embeddings | Atlas Automated Embedding uses Voyage `voyage-4` on the `content` field; documents do not store visible embedding arrays. |
| Governance | Protected governance records add document type, lifecycle status, source authority, and optional authority overrides. |
| Conflict handling | Indexed claim assertions let the app compare stale and current claims deterministically. |
| Security filtering | Retrieval applies `realm_id` and `access_principals` before candidates are ranked. |
| Conversation state | MongoDB stores LangGraph checkpoints and governed semantic memory. |
| Auditability | Final answers are bound only to retrieved MongoDB artifacts, not unsupported model summaries. |

The practical value for customers is lower latency, clearer citations, deterministic conflict handling,
and a reusable architecture for production-style enterprise RAG.

## What the demo proves

- **Latency pattern:** source retrieval can fan out in parallel without waiting for multiple answer-writing agents.
- **Tool boundary:** source-specific components are retrieval tools that return evidence, not prose answers.
- **Governed answers:** policy, implementation, runbook, incident, and discussion evidence can be ranked consistently.
- **Stale-source handling:** old Confluence or Teams guidance can remain visible without winning over current GitHub, Jira, or SharePoint evidence.
- **Targeted routing:** prompts can intentionally search all five sources, or only two or three named sources.
- **Citations:** factual claims in the final response are rebound to verified source artifacts.
- **Operational transparency:** the UI shows a Pipeline Trace with routing, retrieval, reranking, reconciliation, and top evidence.

## Demo source systems

The source systems are simulated with MongoDB Atlas collections. Each one has realistic metadata,
governance, ACLs, and source-specific evidence.

| Source | Represents | Best for showing |
|---|---|---|
| GitHub | Current implementation evidence, commits, service configuration, tests. | What is actually deployed now. |
| Confluence | Architecture pages, design notes, migration guidance, sometimes stale docs. | Design history and stale-vs-current comparisons. |
| Jira | Incidents, rollout tickets, delivery status, remediation records. | Timelines, acceptance evidence, and operational change history. |
| SharePoint | Policies, standards, compliance docs, production runbooks. | Official governance and production-readiness controls. |
| Teams | Operational discussions, incident coordination, informal guidance. | Useful context that may be lower authority or stale. |

The seeded corpus contains `805` artifacts: `161` in each source collection. It includes the original
healthcare scenario records plus five customer-demo source-map artifacts describing the MongoDB-backed
agentic RAG latency story.

## Recommended demo flow

Start the UI and use the sample cards in this order:

1. **Rx auth current state** — shows stale vs current evidence across source systems.
2. **GitHub + Jira auth proof** — shows targeted 2-source routing.
3. **GitHub + Jira + Teams PA events** — shows targeted 3-source routing and operational follow-up.
4. **Merge evidence, not answers** — frames the MongoDB latency and architecture value proposition.
5. **Executive value summary** — produces a customer-ready summary of latency, governance, citations,
   auditability, and operations.

## Sample questions

### Original healthcare tests

- `How do external partners authenticate to the Rx API today, and are any sources outdated?`
- `For prior auth, should clients poll for status or consume events? What changed and when?`
- `Build a timeline from the 60-minute eligibility cache design to the current deployment. Cite the incident, ticket, and implementation.`
- `What is the documented PHI logging policy, and how does it differ from old troubleshooting practices?`

### Targeted source-routing tests

- `Look only in GitHub and Jira. What proves Rx API OAuth 2.0 with PKCE is implemented and deployed?`
- `Look only in SharePoint and Confluence. What is the official PHI logging policy, and how does it compare with troubleshooting guidance?`
- `Look only in GitHub, Jira, and Teams. What changed from prior auth polling to status events, and what operational follow-up is visible?`
- `Look only in Confluence, Jira, and GitHub. Build the eligibility cache timeline from original design to deployed implementation.`

### MongoDB value questions

- `For this customer scenario, how does MongoDB Atlas help replace answer-generating subagents with thin retrieval tools, central reconciliation, and one final grounded answer?`
- `Show how Atlas Search, Vector Search, and rank fusion can merge evidence from GitHub, Confluence, Jira, SharePoint, and Teams before the final LLM call.`
- `What is the benefit of using MongoDB as the shared metadata, search, vector, checkpoint, and memory layer for this agentic RAG workflow?`
- `How should we benchmark intent routing, all-source retrieval, and explicit source selection to prove the MongoDB-backed workflow lowers end-to-end latency?`

## Prerequisites

- Python 3.11+ (the local environment uses Python 3.13).
- MongoDB Atlas 8.0+ with Search, Vector Search, `$rankFusion`, and Automated Embedding
  available (the validated demo cluster runs MongoDB 8.3).
- Voyage indexing and query keys configured for Automated Embedding in Atlas.
  They are configured in Atlas, not passed through this application's CLI.
- A separate application-side Voyage API key for `rerank-3`. Set `VOYAGE_API_KEY`;
  Atlas does not expose its Automated Embedding credentials to the application.
- Either an Azure Grove API key for `gpt-5.6-sol` or a standard OpenAI API key and model.

Automated Embedding is currently an Atlas Public Preview capability. Ensure the
cluster region supports it before bootstrapping.

## How to run the demo

### 1. Configure environment

Copy the example environment file:

```bash
cp .env.example .env
```

Fill in:

- `MONGODB_URI`
- `VOYAGE_API_KEY`
- Grove settings: `CHAT_PROVIDER=grove`, `GROVE_API_KEY`, `GROVE_BASE_URL`, `GROVE_MODEL`
- Or OpenAI settings: `CHAT_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`

Useful demo defaults:

```bash
SOURCE_RETRIEVAL_MODE=hybrid
SOURCE_ROUTING_MODE=intent
SOURCE_TOP_K=5
AUTH_MODE=disabled
```

### 2. Install dependencies

Recommended:

```bash
uv sync --frozen --group dev
```

Legacy pip workflow:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

### 3. Seed Atlas

```bash
.venv/bin/python app.py bootstrap --wait
```

This upserts the source artifacts, protected governance records, claim assertions, validators, five
lexical indexes, five Automated Embedding indexes, and one memory index.

Expected corpus size:

- `805` total source artifacts
- `161` artifacts in each source collection
- `805` governance records
- `805` claim assertions

### 4. Run the Chainlit UI

```bash
.venv/bin/chainlit run chainlit_app.py --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Each response includes a customer-visible **Pipeline Trace** before the final cited answer. Use it to
show source routing, candidate counts, reranking, reconciliation, and top evidence.

### 5. Ask from the CLI

```bash
.venv/bin/python app.py ask "How do external partners authenticate to the Rx API today, and are any sources outdated?"
```

## Demo switches

### Source routing

Set `SOURCE_ROUTING_MODE` to compare routing behavior:

- `intent` — default; the chat provider selects relevant sources.
- `all` — retrieves from all five sources for broad comparison.
- `explicit_only` — uses source names explicitly mentioned in the prompt, otherwise falls back to all sources.

### Retrieval mode

Set `SOURCE_RETRIEVAL_MODE` to compare candidate generation:

- `hybrid` — default; Vector Search + lexical Search + `$rankFusion`.
- `vector` — semantic Vector Search only.
- `lexical` — keyword Atlas Search only.

For customer demos, use `hybrid` as the main path and temporarily switch modes only to explain tradeoffs.

## Validation commands

Run local tests:

```bash
.venv/bin/python -m pytest -q
```

Run lint and type checks:

```bash
.venv/bin/ruff check .
.venv/bin/mypy agent core data db evals scripts ui app.py chainlit_app.py
```

Check Atlas schema, indexes, and counts without printing document content:

```bash
.venv/bin/python -m scripts.check_schema
```

Run a UI smoke test:

```bash
.venv/bin/python -m scripts.smoke_ui
```

Run routing/retrieval benchmark comparisons:

```bash
.venv/bin/python -m scripts.benchmark_modes
```

## Related docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — architecture diagram and implementation details
- [`docs/customer-agentic-rag-latency-guidance.md`](docs/customer-agentic-rag-latency-guidance.md) — customer explanation of the latency pattern
- [`docs/customer-pipeline-code-walkthrough.md`](docs/customer-pipeline-code-walkthrough.md) — code walkthrough for routing, retrieval, reranking, and reconciliation
- [`docs/routing-retrieval-benchmark.md`](docs/routing-retrieval-benchmark.md) — benchmark methodology
- [`docs/production-readiness.md`](docs/production-readiness.md) — production boundaries and readiness checks
- [`SECURITY.md`](SECURITY.md) — security and production release gates
- [`OPERATIONS.md`](OPERATIONS.md) — readiness, restore, deletion, and incident procedures

## Security note

This is a demo. Do not use real PHI or production secrets. Production use requires source-level
authorization propagation, OAuth/OIDC identity, permission-aware retrieval, audit retention, secret
management, PII controls, and evaluation gates.

Never commit `.env` or paste secrets into prompts, shell commands, logs, tickets, or documentation.
