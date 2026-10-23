# Reusable Demo Profiles

This demo is currently seeded as a healthcare / enterprise policy assistant, but the same
architecture can be reused for other customer scenarios. A **demo profile** is the domain-specific
layer that changes the story without changing the core retrieval, reranking, governance, citation,
and memory pipeline.

## What stays the same

The reusable core is:

```text
identity + ACL filters
→ Atlas Automated Embedding
→ Atlas Vector Search + lexical Search
→ MongoDB $rankFusion
→ Voyage rerank-3
→ deterministic reconciliation
→ verified citations
→ governed memory-v2
```

## What a profile changes

| Profile asset | Purpose | Current healthcare example |
|---|---|---|
| Source content | Domain-specific artifacts | Rx auth, prior auth, eligibility cache, PHI logging |
| Source labels | Familiar systems for the customer | GitHub, Confluence, Jira, SharePoint, Teams |
| Authority model | Which source wins during conflict | GitHub implementation, SharePoint policy, Jira delivery tickets |
| Claim keys | Facts to compare across sources | `rx_auth_protocol`, `phi_logging` |
| Contradictions | Deliberate stale/current conflicts | OAuth 1.0 vs OAuth 2 + PKCE |
| Starter prompts | Customer-facing demo questions | PHI policy, cache TTL, event delivery |
| Eval cases | Regression gates | preferred artifact, stale artifact, required terms |
| Presentation story | Customer narrative | governed healthcare platform knowledge |

## Current profile files

The current profile is spread across these files:

- `data/seed_data.py` — synthetic artifacts, claims, metadata, and planted contradictions.
- `db/bootstrap.py` — source authority and freshness settings in `SOURCE_CONFIGS`.
- `chainlit_app.py` — customer-facing starter prompts.
- `evals/cases.json` — deterministic live RAG cases.
- `evals/retrieval_cases.json` — retrieval assurance cases.
- `presentations/` — customer and technical talk tracks.
- `ARCHITECTURE.md` and `README.md` — reusable architecture explanation.

## Profile design checklist

Use this checklist when adapting the demo for a new customer or industry.

### 1. Pick the scenario

Choose a scenario where hybrid search and governance are easy to see:

- multiple systems contain related content
- at least one source has stale or lower-authority guidance
- exact terms or IDs matter
- semantic paraphrases also matter
- citations and access control are important

Good examples:

- financial services policy assistant
- insurance claims knowledge assistant
- developer support assistant
- manufacturing quality assistant
- legal/compliance assistant
- internal IT operations assistant

### 2. Define sources

Keep the current five source keys for the easiest adaptation:

- `github`
- `confluence`
- `jira`
- `sharepoint`
- `teams`

You can relabel the story around them, for example:

- GitHub → implementation evidence
- Confluence → design knowledge
- Jira → delivery / exception evidence
- SharePoint → approved policy
- Teams → informal or historical operational context

Changing the source keys themselves is possible, but it requires updating `ALL_SOURCES`, validators,
index bootstrap logic, UI labels, tests, and seed data.

### 3. Define authority and freshness

Update `SOURCE_CONFIGS` in `db/bootstrap.py` to reflect the profile's trust model.

Example pattern:

- approved policy source: highest authority for policy questions
- implementation source: highest authority for deployed behavior
- ticketing source: strong delivery evidence
- wiki source: useful but more likely stale
- chat source: lowest authority unless it is an incident representative

### 4. Create conflict-ready claims

Each profile should include a few normalized claim keys that can appear across sources.

Examples:

- `authentication_protocol`
- `retention_period`
- `cache_ttl`
- `deployment_status`
- `approved_vendor`
- `incident_response_policy`

For each claim, seed at least:

- one current preferred value
- one stale or conflicting value
- one authoritative representative
- one historical or low-authority representative

### 5. Make hybrid search visible

Seed prompts and artifacts so both retrieval paths matter:

- Semantic path: paraphrased descriptions and related concepts.
- Lexical path: exact policy names, IDs, system names, or compliance phrases.

The Chainlit **Retrieval pipeline** inspector shows whether the turn used hybrid `$rankFusion`,
reranking, fallback behavior, and contradiction detection.

For a live explanation, temporarily switch `SOURCE_RETRIEVAL_MODE`:

- `vector` to show semantic-only retrieval.
- `lexical` to show exact-term-only retrieval.
- `hybrid` to show the default combined path.

Return to `hybrid` before presenting the main governed-answer flow.

### 6. Update starters and evals

For each profile, create starter prompts that demonstrate:

1. current-state answer
2. stale-source conflict
3. exact identifier retrieval
4. semantic paraphrase retrieval
5. governed policy or authority decision
6. multi-turn follow-up

Then update eval cases with:

- preferred claim value
- preferred artifact
- stale artifacts
- required term groups
- citation expectations

### 7. Refresh presentation materials

Update the decks in `presentations/` with:

- customer-specific problem framing
- profile-specific demo script
- key contradiction example
- industry-relevant value statement
- screenshot or architecture diagram if needed

## Recommended implementation path

For the first reusable profile, keep code changes minimal:

1. Rework `data/seed_data.py` for the new domain.
2. Adjust `SOURCE_CONFIGS` authority and freshness values.
3. Update starter prompts in `chainlit_app.py`.
4. Update `evals/cases.json` and `evals/retrieval_cases.json`.
5. Run `app.py bootstrap --wait`.
6. Run tests, retrieval evals, and UI smoke.
7. Update the customer deck and demo script.

After two or more profiles exist, consider extracting the profile assets into separate folders and
adding a `DEMO_PROFILE` setting.