# Security and Data Boundaries

## Deployment status

This repository is a technical demonstration built with deterministic synthetic healthcare
artifacts. It is not approved to process PHI, PII, credentials, or production enterprise
content. Password authentication is demo-grade. Production startup requires OAuth, an allowed
provider, and trusted mapping of identity claims to `realm_id`, `user_id`, and principals.

## Provider data flow

| Boundary | Data sent | Required production decision |
|---|---|---|
| MongoDB Atlas Automated Embedding | Indexed artifact/memory `content` text and search query text are processed by the configured Voyage model integration. Vectors are managed in Atlas Search indexes, not exposed as document fields. | Confirm supported region, preview-feature policy, contractual terms, retention, residency, encryption, and regulated-data eligibility. |
| Application-side Voyage reranking | Rewritten query and ACL-filtered candidate titles/content are sent to Voyage. | Confirm DPA/BAA requirements, retention and training policy, region, egress controls, and incident process. |
| Azure Grove generation | User question, selected evidence, contradiction decisions, and redacted conversational memory are sent to Grove. | Confirm approved model deployment, DPA/BAA, retention and training policy, content filtering, regional routing, and auditability. |
| Chainlit browser session | Draft answer tokens may be displayed locally; production buffers them until deterministic citation binding completes. | Use exact HTTPS origins, enterprise SSO, secure cookies, reverse-proxy hardening, and CSP/TLS controls. |

Atlas lexical and vector filters enforce `realm_id` and `access_principals` before rank fusion.
Application-side reranking occurs only after this authorization boundary. Retrieved content is
treated as untrusted data, not instructions.

Because embeddings are maintained inside Atlas indexes, source documents and memory documents do
not contain visible vector arrays to redact or export. Treat the indexed text and managed vector
index as sensitive derived data for provider review, backup/restore, deletion, and residency
decisions.

## Production release gates

Before real enterprise or regulated data is introduced:

1. Configure the implemented OAuth callback for an approved provider; validate the configured
   realm/group claim names against that provider's signed identity response.
2. Complete provider legal/security review, including BAA/DPA, subprocessor, residency,
   retention, model-training, deletion, and breach-notification terms.
3. Configure Atlas private networking, least-privilege database users, encryption, auditing,
   backup/restore tests, and approved Automated Embedding region/model integration.
4. Store application credentials in an approved secret manager and rotate them through a
   documented process. Never commit `.env`.
5. Add ingress TLS, exact HTTPS origins, rate limiting, session controls, CSP, and centralized
   security monitoring.
6. Validate redaction and DLP controls with representative regulated fields. Regex redaction is
   defense-in-depth, not a complete PHI de-identification system.
7. Run ACL isolation, citation-integrity, load, failure, deletion, and live RAG evaluations in
   the target environment; establish owners, alerts, SLOs, and incident procedures.

## Persistence and deletion

- Source artifacts remain in Atlas until connector lifecycle policies remove them.
- Durable memories are selectively written, redacted, tenant/user scoped, typed, versioned,
  provenance-tagged, validity-bounded, deduplicated or semantically reinforced, and TTL-managed.
- Deletion immediately tombstones and redacts both memory content and summary. Read filters
  exclude deleted or invalid nodes, and a deleted deterministic identity cannot be resurrected.
- LangGraph checkpoints have an independent retention period.
- Thread ownership records make checkpoints tenant-addressable for deletion.
- MongoDB TTL deletion is asynchronous; reads also filter tombstoned and expired memories so
  deleted context is not returned while physical cleanup is pending.

## Logs and citations

Structured degradation logs exclude prompts, retrieved content, credentials, and raw exception
messages. Inline citation URLs are stripped from model output and rebound only from retrieved
artifact metadata. The model-generated Sources section is discarded and rebuilt by the
application.

Connector identities must not write `artifact_governance`, `sources`, or `thread_ownership`.
Reconciliation ignores connector-supplied governance and overlays protected policy records.