# Customer Guidance: Reducing Latency in Multi-Agent RAG

## Executive summary

If a system calls multiple answer-writing subagents, each subagent runs RAG, each subagent writes an
answer, and then a main agent or merge agent combines those answers, latency will usually grow quickly.

The recommendation is:

> Merge evidence, not answers.

Keep the source-specific retrieval work parallel, but move the merge point earlier in the pipeline.
Source-specific components should be thin retrieval tools that return structured evidence, not full
prose answers. The main workflow should deduplicate, rerank, reconcile, and select evidence centrally,
then call one final writer model once.

## Current pattern causing latency

The slower pattern usually looks like this:

1. User asks a question.
2. Main agent decides several answer-writing subagents are needed.
3. Subagent A runs RAG and writes an answer.
4. Subagent B runs RAG and writes an answer.
5. Subagent C runs RAG and writes an answer.
6. A merge agent reads those answers.
7. The merge agent may call another RAG path or another model to produce the final answer.

Each individual subagent response may be good, but the end-to-end system pays for multiple retrieval
calls, multiple generation calls, larger merge context, duplicated evidence, and another synthesis
step.

The deeper issue is architectural: the system is reconciling summaries instead of reconciling source
evidence.

## Recommended pattern

Use this shape instead:

1. User question.
2. Intent and source routing.
3. Parallel retrieval from selected sources.
4. Normalize returned evidence.
5. Deduplicate candidates.
6. Globally rerank all authorized evidence.
7. Reconcile conflicts centrally with deterministic rules.
8. Select the final evidence set and conflict notes.
9. Call one grounded writer model.
10. Verify and bind citations.

The key difference is that source-specific components become thin retrieval tools. They retrieve
evidence from their source, but they do not independently write final answers.

## Why merging answers is expensive

Merging agent-written prose creates several problems:

- every answer-writing subagent spends tokens writing prose that may later be discarded
- the merge agent receives larger context than necessary
- duplicate facts appear in multiple agent responses
- contradictions are embedded inside prose instead of explicit data
- citations can become detached from the original evidence
- the merge agent may need another retrieval call because upstream evidence was summarized away

This increases latency and can reduce trust.

## What each retrieval tool should return

Each source-scoped retrieval tool should return structured evidence like:

- source name
- artifact ID
- title
- URL
- timestamp
- authority or lifecycle metadata
- retrieval score
- rerank score, if available
- claim key and claim value, if applicable
- short snippet
- access-control scope

It should not return a full final answer unless the use case truly needs independent expert opinions.

## Central evidence fusion

After all selected sources return evidence, the main workflow should combine candidates centrally:

1. Deduplicate equivalent artifacts or repeated chunks.
2. Apply one global rerank over all authorized candidates.
3. Score evidence using relevance, authority, and freshness.
4. Detect repeated or conflicting claims.
5. Select preferred/current evidence before generation.
6. Preserve representative conflicting evidence for explanation.

This lets the final model explain the decision instead of making the decision.

## Deterministic reconciliation

Do not ask another LLM to decide which source is true from prose summaries. Use deterministic policy
where possible:

- source authority
- document type
- lifecycle status
- timestamp/freshness
- relevance score
- known claim keys
- policy overrides
- access-control constraints

For example, an approved policy might outrank an old chat message, and a current implementation
record might outrank a stale design document.

## Target architecture

The target architecture is:

`user question → source routing → parallel retrieval → global reranking → deterministic reconciliation → one grounded writer → verified citations`

This keeps the benefit of multiple specialists without paying for multiple full answer-generation
loops.

## Migration plan

### Phase 1: Measure the current pipeline

Capture the number of model calls, retrieval calls, per-agent latency, merge latency, merge-token
volume, duplicate evidence rate, citation precision, and examples where the merge loses important
details.

### Phase 2: Change source-component outputs

Convert answer-writing subagents into evidence-returning retrieval tools. Each should return top
evidence records with metadata, not prose.

### Phase 3: Add global ranking

Pool all authorized evidence and rerank against the original user question. This can use search rank
fusion, a reranker model, deterministic scoring, or a combination.

### Phase 4: Add deterministic conflict policy

Define explicit rules for source authority, freshness, document lifecycle, and policy overrides.

### Phase 5: Generate once

Send only the selected evidence, conflict notes, and citation identifiers to a single final writer
model.

## Quick wins if a full redesign is not possible yet

- Ask source components for cited bullet facts instead of full answers.
- Limit each source retrieval tool to a strict candidate, citation, and latency budget.
- Merge only facts that are tied to citations.
- Cache retrieval results and normalized evidence.
- Avoid merge-time RAG unless the upstream evidence contract is insufficient.

## When answer-writing agents still make sense

Multiple answer-writing agents can be useful for legal review, adversarial critique, planning
alternatives, red-team/blue-team analysis, or independent expert opinions.

For enterprise RAG across knowledge sources, however, the better default is:

> many retrievers, one reconciler, one writer.

## Recommended customer message

Your agents are individually doing useful work, but they are producing the wrong intermediate
artifact. They should not produce full answers for another agent to merge. They should produce
structured evidence. The main workflow should merge evidence, reconcile it centrally, and generate
once.

Do not solve the latency problem by adding a better merge agent. Remove the need for a merge agent.
