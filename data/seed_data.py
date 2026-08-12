from datetime import UTC, datetime, timedelta

from core.schemas import ALL_SOURCES

REFERENCE_NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
DOC_REFS = {
    "rx_partner_auth": [
        "https://www.mongodb.com/docs/atlas/architecture/current/network-security/",
        "https://www.mongodb.com/docs/atlas/architecture/current/security/",
    ],
    "pa_status_delivery": [
        "https://www.mongodb.com/docs/atlas/atlas-stream-processing/",
        "https://www.mongodb.com/docs/manual/changeStreams/",
    ],
    "eligibility_cache": [
        "https://www.mongodb.com/docs/atlas/analyze-slow-queries/",
        "https://www.mongodb.com/docs/manual/core/indexes/index-types/index-ttl/",
    ],
    "phi_logging": [
        "https://www.mongodb.com/docs/atlas/architecture/current/auditing/",
        "https://www.mongodb.com/docs/atlas/architecture/current/data-encryption/",
    ],
}


def _source_metadata(source: str, key: str, metadata: dict) -> dict:
    defaults: dict[str, dict] = {
        "github": {"repo": "cmm-health-platform", "branch": "main",
                   "path": f"services/{key}/README.md", "commit": f"{sum(map(ord, key)):07x}",
                   "pull_request": f"PR-{sum(map(ord, key)) % 900 + 100}"},
        "confluence": {"space": "DATA-PLATFORM", "page_id": str(700000 + sum(map(ord, key))),
                       "hierarchy": ["Enterprise Data Platform", "Healthcare Integrations"],
                       "version": 7, "owner": "Platform Architecture"},
        "jira": {"project": "PLAT", "issue_key": key.upper(), "status": "Done",
                 "status_category": "Complete", "resolution": "Deployed"},
        "sharepoint": {"site": "Enterprise Architecture", "library": "Approved Standards",
                       "folder": "/MongoDB Atlas/Healthcare", "owner": "Data Governance",
                       "review_cadence": "quarterly", "approval_status": "Approved"},
        "teams": {"team": "MongoDB Data Platform", "channel": "healthcare-applications",
                  "thread_id": f"thread-{key}", "participants": 6, "reply_count": 11},
    }
    return {**defaults[source], **metadata}


def _artifact(source: str, key: str, title: str, content: str, days_old: int,
              claims: dict[str, str] | None = None, **metadata) -> dict:
    extensions = {"github": "blob", "confluence": "pages", "jira": "browse",
                  "sharepoint": "sites", "teams": "channels"}
    author = metadata.pop("author", "CMM Demo Team")
    governance = metadata.pop("governance", {
        "document_type": "reference", "lifecycle_status": "active",
    })
    theme = metadata.get("theme")
    if theme:
        metadata.setdefault("documentation_refs", DOC_REFS[theme])
    metadata.setdefault("synthetic", True)
    metadata = _source_metadata(source, key, metadata)
    return {
        "artifact_id": f"{source}-{key}", "source": source, "title": title,
        "content": content,
        "url": f"https://demo.cmm.local/{source}/{extensions[source]}/{key}",
        "author": author,
        "created_at": REFERENCE_NOW - timedelta(days=days_old + 30),
        "updated_at": REFERENCE_NOW - timedelta(days=days_old),
        "claims": claims or {}, "metadata": metadata, "governance": governance,
    }


def core_artifacts() -> list[dict]:
    return [
        _artifact("github", "rx-auth-implementation", "Rx API authentication middleware",
            "Production middleware validates OAuth 2.0 access tokens and requires PKCE for public clients. OAuth 1.0 code was removed in PR 842.", 5,
            {"rx_auth_protocol": "oauth2_pkce"}, theme="rx_partner_auth",
            repo="rx-api", branch="main", path="src/auth/middleware.py", commit="f8c219a"),
        _artifact("confluence", "legacy-rx-auth", "Rx API integration guide (legacy)",
            "Partners authenticate to Rx API with OAuth 1.0 signed requests. Migration planning is pending.", 980,
            {"rx_auth_protocol": "oauth1"}, theme="rx_partner_auth", space="RX",
            status="legacy", version=2, owner="Partner Integration Team"),
        _artifact("teams", "auth-migration-chat", "Rx platform auth migration thread",
            "I think the partner gateway still needs OAuth 1.0; that was true during last year's incident.", 420,
            {"rx_auth_protocol": "oauth1"}, theme="rx_partner_auth", channel="rx-platform",
            participants=4, reply_count=8),
        _artifact("jira", "RX-842", "Complete OAuth2 + PKCE migration",
            "Migration completed and deployed. OAuth 1.0 compatibility was removed after partner certification.", 12,
            {"rx_auth_protocol": "oauth2_pkce"}, theme="rx_partner_auth", project="RX",
            issue_key="RX-842", status="Done", linked_artifacts=["github-rx-auth-implementation"]),

        _artifact("github", "pa-status-events", "Prior authorization status event publisher",
            "The PA service publishes status changes to the pa.status.changed Atlas Stream Processing pipeline. The polling endpoint is deprecated.", 8,
            {"pa_status_delivery": "events"}, theme="pa_status_delivery", repo="pa-service",
            branch="main", path="src/events/status_publisher.py", commit="17de920"),
        _artifact("confluence", "pa-polling-runbook", "PA status polling runbook",
            "Consumers should poll GET /pa/{id}/status every 30 seconds until a terminal state is reached.", 760,
            {"pa_status_delivery": "polling"}, theme="pa_status_delivery", space="PA",
            status="unverified", version=3, owner="Legacy PA Operations"),
        _artifact("jira", "PA-2194", "Move PA status consumers to events",
            "All tier-1 consumers moved to pa.status.changed. Polling endpoint marked deprecated; removal scheduled for Q4.", 25,
            {"pa_status_delivery": "events"}, theme="pa_status_delivery", project="PA",
            issue_key="PA-2194", status="Done", linked_artifacts=["github-pa-status-events"]),
        _artifact("sharepoint", "pa-integration-standard", "PA integration standard 2026",
            "New PA integrations must consume status events from the managed stream. Polling is allowed only under an approved exception.", 45,
            {"pa_status_delivery": "events"}, theme="pa_status_delivery",
            library="Architecture Standards", review_cadence="semiannual"),

        _artifact("github", "logging-redaction", "Gateway structured logging filter",
            "Request bodies and PHI fields are redacted before log emission. Raw payload logging is disabled in every environment.", 3,
            {"phi_logging": "redacted"}, theme="phi_logging", repo="api-gateway",
            branch="main", path="src/logging/phi_redaction.py", commit="ca981d4",
            governance={"document_type": "implementation", "lifecycle_status": "active",
                        "authority_override": 0.95}),
        _artifact("sharepoint", "phi-logging-policy", "Enterprise PHI logging policy",
            "PHI must never be written to application logs. Approved structured fields must pass the redaction filter.", 30,
            {"phi_logging": "redacted"}, theme="phi_logging", library="Security Policies",
            folder="/Security/PHI", owner="Chief Information Security Office",
            governance={"document_type": "policy", "lifecycle_status": "effective",
                        "authority_override": 1.0}),
        _artifact("teams", "debug-payloads", "Troubleshooting payload failures",
            "During the 2023 outage someone suggested temporarily logging full request bodies to diagnose malformed payloads.", 1150,
            {"phi_logging": "raw_payloads"}, theme="phi_logging", channel="incident-2023",
            participants=12, reply_count=37,
            governance={"document_type": "incident_thread", "lifecycle_status": "historical",
                        "authority_override": 0.15}),
        _artifact("confluence", "phi-troubleshooting", "PHI-safe troubleshooting guide",
            "Troubleshooting uses correlation IDs, redacted structured events, and Atlas database audit records. Raw payloads are prohibited.", 55,
            {"phi_logging": "redacted"}, theme="phi_logging", space="SEC",
            owner="Security Engineering", version=11,
            governance={"document_type": "runbook", "lifecycle_status": "effective",
                        "authority_override": 0.85}),

        _artifact("github", "eligibility-cache", "Eligibility cache configuration",
            "Eligibility responses use a 5-minute TTL. Negative responses use a 30-second TTL to avoid stale denials.", 14,
            {"eligibility_cache_ttl": "5_minutes"}, theme="eligibility_cache",
            repo="eligibility-api", branch="main", path="config/cache.py", commit="b41a8ce"),
        _artifact("confluence", "eligibility-cache-design", "Eligibility caching design",
            "The initial design proposes a 60-minute cache to reduce payer traffic.", 640,
            {"eligibility_cache_ttl": "60_minutes"}, theme="eligibility_cache", space="ELIG",
            version=1, status="superseded", owner="Eligibility Architecture"),
        _artifact("jira", "ELIG-388", "Reduce eligibility cache TTL",
            "Changed positive-response cache from 60 minutes to 5 minutes after stale coverage incidents.", 20,
            {"eligibility_cache_ttl": "5_minutes"}, theme="eligibility_cache", project="ELIG",
            issue_key="ELIG-388", status="Done", linked_artifacts=["github-eligibility-cache"]),
        _artifact("teams", "eligibility-stale-incident", "Stale eligibility incident thread",
            "The incident review confirms the old 60-minute cache served stale coverage. The production value is now 5 minutes.", 35,
            {"eligibility_cache_ttl": "5_minutes"}, theme="eligibility_cache",
            channel="eligibility-incidents", participants=9, reply_count=24),
    ]


SUPPORTING_FACTS = {
    "rx_partner_auth": [
        ("partner-onboarding", "Rx partner onboarding controls",
         "Production partners use OAuth 2.0 with PKCE; Atlas connectivity uses mandatory TLS and private endpoints."),
        ("contract-validation", "Rx authentication contract validation",
         "Certification rejects OAuth 1.0 signatures and verifies OAuth 2.0 token audience, expiry, and PKCE challenge."),
    ],
    "pa_status_delivery": [
        ("event-operations", "PA event delivery operations",
         "Prior authorization status changes flow through pa.status.changed; consumers use idempotent handlers and a dead-letter queue."),
        ("polling-retirement", "PA polling retirement evidence",
         "Operational dashboards track stream lag and delivery failures; repeated status polling is deprecated for new consumers."),
    ],
    "eligibility_cache": [
        ("cache-operations", "Eligibility cache operational controls",
         "Positive eligibility responses expire after 5 minutes and negative responses after 30 seconds; cache lookups are indexed."),
        ("stale-coverage", "Eligibility stale coverage prevention",
         "The former 60-minute TTL caused stale benefit decisions, so the deployed positive-response TTL is 5 minutes."),
    ],
    "phi_logging": [
        ("data-protection", "PHI data protection controls",
         "Atlas data uses TLS and encryption at rest; application telemetry permits only redacted structured fields and correlation IDs."),
        ("audit-controls", "PHI audit and troubleshooting controls",
         "Database auditing records access and privilege changes while raw request or response payload logging remains prohibited."),
    ],
}

CLAIMS = {
    "rx_partner_auth": {"rx_auth_protocol": "oauth2_pkce"},
    "pa_status_delivery": {"pa_status_delivery": "events"},
    "eligibility_cache": {"eligibility_cache_ttl": "5_minutes"},
    "phi_logging": {"phi_logging": "redacted"},
}

EXTRA_ARTIFACTS = [
    ("github", "rx-partner-sdk", "Rx partner SDK release notes", "The supported SDK implements OAuth 2.0 authorization code flow with PKCE and has no OAuth 1.0 signer.", 17, "rx_partner_auth"),
    ("sharepoint", "rx-network-standard", "Rx Atlas network standard", "Production Rx workloads reach Atlas through private endpoints with mandatory TLS; public ingress is not approved.", 28, "rx_partner_auth"),
    ("confluence", "pa-event-architecture", "PA event architecture decision", "The approved design uses change events and Atlas Stream Processing for validation, routing, and dead-letter handling.", 38, "pa_status_delivery"),
    ("teams", "pa-cutover-thread", "PA event cutover support thread", "Tier-1 consumers confirmed pa.status.changed delivery; the team is removing residual polling alerts.", 31, "pa_status_delivery"),
    ("jira", "ELIG-411", "Validate eligibility TTL after incident", "Load and correctness tests passed with a 5-minute positive cache and 30-second negative cache.", 16, "eligibility_cache"),
    ("teams", "eligibility-support-bulletin", "Eligibility support bulletin", "Support should invalidate affected entries, not extend the cache; production positive TTL remains 5 minutes.", 24, "eligibility_cache"),
    ("sharepoint", "phi-audit-standard", "Atlas PHI audit standard", "Production projects enable database auditing for access and security events; application logs remain redacted.", 22, "phi_logging"),
    ("jira", "SEC-631", "Enforce PHI log redaction", "Redaction tests, audit filters, and alerting were deployed. Raw payload debug flags were removed.", 9, "phi_logging"),
]

PLATFORM_APPLICATIONS = [
    ("partner-gateway", "Partner Integration Gateway", "external pharmacy and payer APIs"),
    ("member-api", "Member API", "member eligibility and benefit experiences"),
    ("provider-api", "Provider API", "provider-facing clinical workflows"),
    ("pharmacy-hub", "Pharmacy Transaction Hub", "real-time pharmacy transactions"),
    ("claims-service", "Claims Service", "medical and pharmacy claim adjudication"),
    ("benefits-engine", "Benefits Engine", "plan benefit determination"),
    ("formulary-service", "Formulary Service", "drug coverage and restriction data"),
    ("care-management", "Care Management", "longitudinal care workflows"),
    ("clinical-documents", "Clinical Document Service", "FHIR and clinical documents"),
    ("patient-messaging", "Patient Messaging", "regulated member communications"),
    ("provider-directory", "Provider Directory", "network and credential information"),
    ("payment-integrity", "Payment Integrity", "fraud, waste, and abuse analytics"),
    ("consent-service", "Consent Service", "member consent and data-use directives"),
    ("identity-service", "Identity Service", "workforce and customer identity mappings"),
    ("notification-service", "Notification Service", "event-driven delivery notifications"),
    ("member-portal", "Member Portal", "web self-service experiences"),
    ("provider-portal", "Provider Portal", "provider self-service experiences"),
    ("mobile-platform", "Mobile Platform", "member mobile applications"),
    ("interoperability-hub", "Interoperability Hub", "FHIR and partner data exchange"),
    ("enterprise-reporting", "Enterprise Reporting", "regulated operational reporting"),
    ("data-lakehouse", "Healthcare Lakehouse", "historical analytics and archive data"),
    ("audit-platform", "Audit Platform", "compliance evidence and investigations"),
    ("integration-runtime", "Integration Runtime", "shared service orchestration"),
    ("operations-console", "Operations Console", "production support and observability"),
]

EVIDENCE_KINDS = [
    ("implementation", "Implementation record", "The deployed service configuration and automated tests enforce"),
    ("architecture", "Architecture decision", "The approved target architecture standardizes"),
    ("rollout", "Rollout record", "The completed rollout and acceptance evidence confirm"),
    ("operations", "Operations runbook", "The production operating procedure requires"),
    ("compliance", "Compliance control", "The quarterly control review verified"),
    ("incident-review", "Incident follow-up", "The corrective-action review reaffirmed"),
]

THEME_TITLES = {
    "rx_partner_auth": "Rx partner authentication",
    "pa_status_delivery": "Prior authorization status delivery",
    "eligibility_cache": "Eligibility cache strategy",
    "phi_logging": "PHI logging and audit policy",
}

THEME_CURRENT_STATE = {
    "rx_partner_auth": "OAuth 2.0 with PKCE, mandatory TLS, and private Atlas connectivity",
    "pa_status_delivery": "pa.status.changed events with idempotent consumers and dead-letter handling instead of polling",
    "eligibility_cache": "a 5-minute positive eligibility TTL and a 30-second negative TTL",
    "phi_logging": "redacted structured logs, correlation IDs, and Atlas database auditing with no raw PHI payloads",
}

THEME_ACCESS_PRINCIPALS = {
    "rx_partner_auth": "role:integration-engineer",
    "pa_status_delivery": "role:clinical-operations",
    "eligibility_cache": "role:benefits-operations",
    "phi_logging": "role:security",
}

ASSURANCE_CONTROLS = {
    "rx_partner_auth": [
        ("token-validation", "Token validation baseline", "implementation", "active",
         "Access tokens require issuer, audience, signature, expiry, and scope validation; public clients also require PKCE."),
        ("partner-onboarding", "Partner onboarding control", "runbook", "effective",
         "Partner onboarding verifies redirect URIs, approved scopes, PKCE capability, and production support ownership before activation."),
        ("scope-governance", "OAuth scope governance", "policy", "effective",
         "Least-privilege scopes are approved per partner and cannot be broadened without security and product-owner review."),
        ("key-rotation", "Signing-key rotation", "runbook", "effective",
         "JWKS caching, overlapping key rotation, unknown-key refresh, and rotation alerts prevent authentication outages."),
        ("network-controls", "Partner network controls", "architecture", "effective",
         "Production partner traffic requires TLS, managed ingress, rate limits, and private Atlas connectivity for backend data access."),
        ("legacy-removal", "OAuth 1 retirement evidence", "deprecation", "effective",
         "OAuth 1 signing code, secrets, documentation, and compatibility tests are removed from supported production paths."),
        ("negative-testing", "Authentication negative tests", "validation", "active",
         "Automated tests reject invalid signatures, missing PKCE verifiers, expired tokens, audience mismatch, and excessive scopes."),
        ("auth-incident", "Authentication incident response", "runbook", "effective",
         "Responders revoke affected credentials, inspect correlation and audit records, rotate keys, and never restore OAuth 1 fallback."),
    ],
    "pa_status_delivery": [
        ("event-contract", "Status event contract", "architecture", "effective",
         "The versioned pa.status.changed contract carries transition, timestamp, correlation ID, and source identifiers."),
        ("idempotency", "Consumer idempotency", "implementation", "active",
         "Consumers deduplicate event identifiers and apply monotonic transition checks before updating prior authorization state."),
        ("dead-letter", "Dead-letter and replay", "runbook", "effective",
         "Failed events enter a monitored dead-letter path with bounded retries, replay authorization, and audit evidence."),
        ("consumer-onboarding", "Event consumer onboarding", "runbook", "effective",
         "New consumers validate schemas, idempotency, replay behavior, ownership, and production alert routing before subscription."),
        ("polling-exception", "Polling exception governance", "policy", "effective",
         "Polling is prohibited for new integrations unless a time-bounded exception has an owner and event-migration date."),
        ("delivery-slo", "Event delivery SLO", "compliance", "effective",
         "Operations monitor publish latency, consumer lag, dead-letter depth, and terminal-state delivery against approved thresholds."),
        ("schema-evolution", "Event schema evolution", "architecture", "effective",
         "Backward-compatible schema changes use versioned contracts and consumer validation before incompatible fields are removed."),
        ("delivery-recovery", "Status delivery recovery", "runbook", "effective",
         "Recovery restores checkpoints, replays retained events in order, verifies idempotency, and reconciles terminal statuses."),
    ],
    "eligibility_cache": [
        ("ttl-baseline", "Eligibility TTL baseline", "policy", "effective",
         "Positive eligibility results expire after five minutes and negative results after thirty seconds."),
        ("cache-key", "Eligibility cache-key isolation", "architecture", "effective",
         "Cache keys include tenant, member, plan, coverage period, and payer dimensions to prevent cross-context reuse."),
        ("invalidation", "Eligibility invalidation events", "implementation", "active",
         "Coverage-change and correction events invalidate affected entries before their normal expiration window."),
        ("stale-response", "Stale response prevention", "policy", "effective",
         "Expired eligibility data cannot be served as current, and stale-if-error behavior requires an explicit approved exception."),
        ("cache-protection", "Cached PHI protection", "compliance", "effective",
         "Cached eligibility data is encrypted, access-scoped, minimally retained, and excluded from diagnostic payload logging."),
        ("cache-observability", "Cache correctness monitoring", "operations", "active",
         "Metrics track age, hit rate, invalidations, negative-cache use, payer errors, and stale-decision prevention."),
        ("cache-incident", "Cache incident playbook", "runbook", "effective",
         "Responders invalidate impacted entries, disable unsafe cache paths, verify payer truth, and document member impact."),
        ("cache-testing", "Eligibility cache validation", "validation", "active",
         "Tests cover positive and negative TTLs, isolation dimensions, invalidation races, clock boundaries, and outage behavior."),
    ],
    "phi_logging": [
        ("prohibited-fields", "Prohibited logging fields", "policy", "effective",
         "Application logs prohibit raw request bodies, clinical content, identifiers, credentials, tokens, and unapproved free text."),
        ("redaction-filter", "Structured redaction filter", "implementation", "active",
         "A centralized allowlist and redaction filter removes PHI and secrets before structured events leave the process."),
        ("correlation", "Correlation-based troubleshooting", "runbook", "effective",
         "Support uses correlation IDs, safe event codes, bounded metadata, and approved traces instead of payload inspection."),
        ("database-audit", "Atlas audit evidence", "compliance", "effective",
         "Atlas auditing records authentication, authorization, and administrative events without copying PHI into application logs."),
        ("break-glass", "Break-glass logging prohibition", "policy", "effective",
         "Incident urgency does not authorize raw PHI logging; emergency diagnostics use approved secure evidence channels."),
        ("log-retention", "Log retention and access", "policy", "effective",
         "Redacted logs have bounded retention, role-scoped access, monitored exports, and documented disposal controls."),
        ("dlp-testing", "Logging DLP validation", "validation", "active",
         "Automated canary tests inject representative sensitive fields and fail releases if telemetry exposes prohibited values."),
        ("logging-incident", "Logging exposure response", "runbook", "effective",
         "Responders stop emission, restrict access, preserve audit evidence, rotate exposed secrets, and follow breach assessment."),
    ],
}

SOURCE_ASSURANCE_NOTES = {
    "github": "Repository controls and automated tests provide implementation evidence.",
    "confluence": "The maintained design record explains ownership and operating intent.",
    "jira": "Completed delivery and control-review issues provide acceptance evidence.",
    "sharepoint": "The approved standard records governance, review, and effective requirements.",
    "teams": "The support record confirms communicated production procedures and ownership.",
}


def assurance_artifacts() -> list[dict]:
    """Add 160 governed assurance artifacts: 40 per theme and 32 per source."""
    rows = []
    for theme_index, (theme, controls) in enumerate(ASSURANCE_CONTROLS.items()):
        for source_index, source in enumerate(ALL_SOURCES):
            for control_index, (slug, title, document_type, status, detail) in enumerate(controls):
                rows.append(_artifact(
                    source, f"assurance-{theme}-{slug}-{source}",
                    f"{THEME_TITLES[theme]} — {title} — {source.title()}",
                    f"{detail} {SOURCE_ASSURANCE_NOTES[source]}",
                    75 + theme_index * 19 + source_index * 11 + control_index * 13,
                    CLAIMS[theme], theme=theme, corpus_phase="assurance-expansion",
                    assurance_dimension=slug,
                    governance={
                        "document_type": document_type,
                        "lifecycle_status": status,
                    },
                    related_artifacts=[f"github-{theme}-{SUPPORTING_FACTS[theme][0][0]}-github"],
                ))
    return rows


def scaled_enterprise_artifacts() -> list[dict]:
    """Add 576 application/evidence records to the deterministic corpus."""
    rows = []
    ordinal = 0
    source_offset = ALL_SOURCES.index("sharepoint")
    for theme_index, theme in enumerate(SUPPORTING_FACTS):
        for app_index, (app_slug, app_name, workload) in enumerate(PLATFORM_APPLICATIONS):
            for evidence_index, (kind, kind_title, framing) in enumerate(EVIDENCE_KINDS):
                source = ALL_SOURCES[(source_offset + ordinal) % len(ALL_SOURCES)]
                key = f"scale-{theme}-{app_slug}-{kind}"
                content = (
                    f"For {app_name}, which supports {workload}, {framing} "
                    f"{THEME_CURRENT_STATE[theme]}. This record belongs to deployment cohort "
                    f"{theme_index + 1}.{app_index + 1} and links the enterprise control to production evidence."
                )
                rows.append(_artifact(
                    source, key, f"{THEME_TITLES[theme]} — {app_name} — {kind_title}",
                    content, 120 + ((ordinal + evidence_index * 17) % 540),
                    CLAIMS[theme], theme=theme, application=app_slug,
                    evidence_kind=kind, deployment_cohort=f"wave-{app_index % 6 + 1}",
                    related_artifacts=[
                        f"github-{theme}-{SUPPORTING_FACTS[theme][0][0]}-github"
                    ],
                ))
                ordinal += 1
    return rows


def supporting_artifacts() -> list[dict]:
    rows = []
    for theme_index, (theme, facts) in enumerate(SUPPORTING_FACTS.items()):
        for source_index, source in enumerate(ALL_SOURCES):
            for fact_index, (slug, title, detail) in enumerate(facts):
                source_note = {
                    "github": "Main-branch code, tests, and deployment configuration confirm this control.",
                    "confluence": "The maintained architecture page explains this operating model.",
                    "jira": "The completed delivery issue records rollout and acceptance evidence.",
                    "sharepoint": "The approved enterprise standard defines this requirement.",
                    "teams": "The engineering support thread confirms current production behavior.",
                }[source]
                rows.append(_artifact(
                    source, f"{theme}-{slug}-{source}", f"{title} — {source.title()}",
                    f"{detail} {source_note}",
                    40 + theme_index * 23 + source_index * 7 + fact_index * 11,
                    CLAIMS[theme], theme=theme,
                    related_artifacts=[f"github-{theme}-{facts[0][0]}-github"],
                ))
    for extra_source, key, title, content, days_old, theme in EXTRA_ARTIFACTS:
        rows.append(_artifact(
            extra_source, key, title, content, days_old, CLAIMS[theme], theme=theme,
            related_artifacts=[f"github-{theme}-{SUPPORTING_FACTS[theme][0][0]}-github"],
        ))
    return rows


def all_artifacts(realm_id: str) -> list[dict]:
    rows = (
        core_artifacts() + supporting_artifacts()
        + scaled_enterprise_artifacts() + assurance_artifacts()
    )
    for row in rows:
        row["realm_id"] = realm_id
        row["access_principals"] = [
            "role:platform-engineer",
            THEME_ACCESS_PRINCIPALS[row["metadata"]["theme"]],
        ]
    return rows
