# Security and Data Boundaries

## Deployment status

This repository is a technical demonstration built with deterministic synthetic healthcare
artifacts. It is not approved to process PHI, PII, credentials, or production enterprise
content. Password authentication is demo-grade; internet-facing deployment requires enterprise
OAuth/OIDC and trusted mapping of identity claims to `realm_id`, `user_id`, and principals.

## Provider data flow

| Boundary | Data sent | Required production decision |
|---|---|---|
| MongoDB Atlas Automated Embedding | Indexed artifact text and search query text are processed by the configured Voyage model integration. | Confirm supported region, preview-feature policy, contractual terms, retention, residency, encryption, and regulated-data eligibility. |
| Application-side Voyage reranking | Rewritten query and ACL-filtered candidate titles/content are sent to Voyage. | Confirm DPA/BAA requirements, retention and training policy, region, egress controls, and incident process. |
| Azure Grove generation | User question, selected evidence, contradiction decisions, and redacted conversational memory are sent to Grove. | Confirm approved model deployment, DPA/BAA, retention and training policy, content filtering, regional routing, and auditability. |
| Chainlit browser session | Draft answer tokens may be displayed locally; production buffers them until deterministic citation binding completes. | Use exact HTTPS origins, enterprise SSO, secure cookies, reverse-proxy hardening, and CSP/TLS controls. |

Atlas vector prefilters enforce `realm_id` and `access_principals` before similarity ranking.
Application-side reranking occurs only after this authorization boundary. Retrieved content is
treated as untrusted data, not instructions.

## Production release gates

Before real enterprise or regulated data is introduced:

1. Replace password auth with enterprise OAuth/OIDC; derive tenant and group principals only
   from validated identity-provider claims.
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
- Semantic memories are redacted, tenant/user scoped, content-deduplicated, bounded,
  tombstoned on deletion, and assigned an expiry timestamp.
- LangGraph checkpoints have an independent retention period.
- MongoDB TTL deletion is asynchronous; reads also filter tombstoned and expired memories so
  deleted context is not returned while physical cleanup is pending.

## Logs and citations

Structured degradation logs exclude prompts, retrieved content, credentials, and raw exception
messages. Inline citation URLs are stripped from model output and rebound only from retrieved
artifact metadata. The model-generated Sources section is discarded and rebuilt by the
application.