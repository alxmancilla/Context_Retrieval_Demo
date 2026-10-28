# Routing and Retrieval Benchmark Guide

Use this guide to turn the demo's routing and retrieval comparison switches into repeatable evidence.
The goal is to show when the extra source-routing model call helps, when all-source retrieval is safer,
and why hybrid Atlas retrieval remains the recommended default.

## What to compare

| Mode family | Values | Question answered |
|---|---|---|
| `SOURCE_ROUTING_MODE` | `intent`, `all`, `explicit_only` | Does routing reduce latency/cost without missing required evidence? |
| `SOURCE_RETRIEVAL_MODE` | `hybrid`, `vector`, `lexical` | Does `$rankFusion` outperform either retrieval path alone? |

Default benchmark coverage runs five combinations:

| Purpose | Routing | Retrieval |
|---|---|---|
| normal path | `intent` | `hybrid` |
| all-source recall comparison | `all` | `hybrid` |
| expert explicit-source comparison | `explicit_only` | `hybrid` |
| semantic-only retrieval comparison | `intent` | `vector` |
| lexical-only retrieval comparison | `intent` | `lexical` |

Use `--full-matrix` only when you want all nine routing/retrieval combinations.

## Command

Run after `.env` is configured and Atlas/Grove or OpenAI/Voyage are reachable:

`.venv/bin/python -m scripts.benchmark_modes`

Optional full matrix:

`.venv/bin/python -m scripts.benchmark_modes --full-matrix`

The script writes ignored JSON files under `evals/results/`. It reuses the existing metric-only live
RAG evaluator and does not print model answers, document content, headers, or secrets.

## Metrics to inspect

Each row records:

- `source_routing_mode`
- `source_retrieval_mode`
- `total` and `passed` case counts
- `pass_rate`
- output path for the detailed per-case metric file

Open each detailed output to compare latency, required-term coverage, verified citation precision,
contradiction resolution, representative selection, stale-evidence identification, degradation, and
source-appendix size.

## Interpretation

- Prefer `intent + hybrid` for the normal demo when it passes all cases and improves latency/cost.
- Use `all + hybrid` for audit-style runs where recall matters more than cost.
- Use `explicit_only + hybrid` for expert prompts that name systems directly.
- Use `vector` and `lexical` only as ablations; return to `hybrid` for governed answers.
- Treat any missed contradiction, stale evidence, or verified citation failure as a release-blocking
  quality signal, even if latency improves.

## Suggested report table

| Routing | Retrieval | Passed | p95/latency note | Quality note | Decision |
|---|---|---:|---|---|---|
| `intent` | `hybrid` | _fill from JSON_ | _fill_ | _fill_ | default candidate |
| `all` | `hybrid` | _fill_ | _fill_ | _fill_ | audit fallback |
| `explicit_only` | `hybrid` | _fill_ | _fill_ | _fill_ | expert prompt option |
| `intent` | `vector` | _fill_ | _fill_ | _fill_ | ablation only |
| `intent` | `lexical` | _fill_ | _fill_ | _fill_ | ablation only |