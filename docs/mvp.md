# MVP Scope

This MVP implements a vendor due-diligence gate with deterministic rule evaluation, risk-banded escalation, human review routing, and auditable lifecycle tracking.

## Current Program Scope

The implemented program focuses on vendor spend and due-diligence gating rather than employee conduct.

- business activity: intake and gating of purchase orders and vendor transactions before spend is incurred
- compliance problem: spend requires consistent approval-threshold enforcement, vendor due-diligence screening, and accountable escalation
- agent role: evaluate transaction submissions, route reviews, and maintain a complete audit trail

## In-Scope Controls

- PROC-SPEND-APPROVAL-001: purchase-order spend-approval threshold and dual-approval enforcement
- PROC-VENDOR-DUEDILIGENCE-001: vendor due-diligence and sanctions/watchlist screening requirements
- PROC-INTL-VENDOR-001: jurisdiction-specific enhanced due-diligence, driven by a versioned high-risk country-code list in the rule catalog rather than a caller-supplied risk flag
- PROC-VENDOR-COI-001: conflict-of-interest disclosure and compliance clearance requirements when a potential conflict between requestor and vendor is flagged
- PROC-EXPENSE-RECEIPT-001: itemized receipt documentation and amount-reconciliation requirements for expenses at or above the receipt threshold
- PROC-PART-TIME-CONTRACT-001: worker-classification risk assessment requirements for vendor engagements structured as part-time contract or temporary staffing arrangements
- PROC-GIFTS-HOSPITALITY-001: pre-approval requirements for gifts, hospitality, or entertainment given to or received from a vendor, with a zero-amount threshold when the counterparty is a government official
- PROC-VENDOR-PAYMENT-CHANGE-001: independent verification requirements for changes to a vendor's payment/banking details, to guard against business-email-compromise-style payment redirection fraud

## Decision Outcomes

- approved
- blocked
- insufficient_evidence
- human_review_required

## Escalation Notifications

- each control's rule catalog carries a `notification_recipients` policy under `escalation_triggers`, mapping risk band to stakeholder groups (`procurement`, `legal`, `finance`)
- `evaluate_vendor_case` computes `escalation_recipients` on every `DecisionRecord` from that policy after the deterministic evaluator runs, so it's uniform across all eight evaluators rather than duplicated per control
- a LOW-band decision always resolves to no recipients; a control with no configured policy for a band also resolves to no recipients rather than guessing
- this is a computed, auditable routing field today, not a sent notification — see README "Next steps" for wiring it to an actual outbound channel

## Regulatory Sourcing and the Internal-Policy Layer (Barbados/Caribbean, for now)

Each control's `data/rules/*.json` catalog carries a `policy_references` list (`RuleMetadata.policy_references` in `app/models.py`, a list of `PolicyReference` entries tagged `external_regulation` or `internal_policy`, each with `citation`/`jurisdiction`/`source_url`/`notes`), so every rule evaluation maps back to something citable rather than an invented label. These were researched, not assumed:

- **Barbados Public Procurement Act, 2021 (Act No. 30 of 2021)** and the **CARICOM Protocol on Procurement** — `PROC-SPEND-APPROVAL-001`, `PROC-INTL-VENDOR-001`
- **Money Laundering and Financing of Terrorism (Prevention and Control) Act, 2011-23** and **CFATF** (Caribbean Financial Action Task Force) FATF-Recommendations compliance — `PROC-VENDOR-DUEDILIGENCE-001`, `PROC-INTL-VENDOR-001`
- **Employment Rights Act, 2012 (Act 2012-9)** — `PROC-PART-TIME-CONTRACT-001`
- **Prevention of Corruption Act, 2021 (Barbados)** — `PROC-GIFTS-HOSPITALITY-001`; covers bribery/gifts to both public officials and private-sector counterparties, with real criminal penalties (up to BBD$1,500,000 or 15 years on indictment) and corporate liability
- **Computer Misuse Act, Chapter 124B**, the **National Payment System Act, 2021**, and the MLFTA above — `PROC-VENDOR-PAYMENT-CHANGE-001`; the Computer Misuse Act specifically criminalizes computer-related fraud, directly on-point for business-email-compromise-style payment redirection

Two honesty gaps, left as gaps rather than papered over: no confirmed, currently-enacted Barbados private-sector conflict-of-interest statute was found (the Integrity in Public Life Bill failed in the Senate in 2020 and was reintroduced in 2023, but Senate passage/entry into force wasn't confirmed, so it isn't cited), so `PROC-VENDOR-COI-001` is internal-policy-only; and no dedicated Barbados receipt-documentation statute was found, so `PROC-EXPENSE-RECEIPT-001` is internal-policy-only too.

None of the researched sources gave a verified numeric threshold (a specific dollar approval amount, a specific part-time-hours cutoff), so every threshold in `escalation_triggers` remains an internal-policy value — nothing here should be read as a legally-mandated number. An `external_regulation` reference may declare `minimum_threshold_field`/`minimum_threshold_value` when a real, verified numeric floor exists for one of the rule's trigger keys; none currently do.

`validate_no_internal_policy_conflicts()` (`app/engine.py`) checks every loaded rule's trigger values against any such declared floor, and `load_rules()` raises if an internal value is ever looser than the regulatory minimum — the "space to add internal rules... once it bears no conflict" is enforced structurally, not just documented, and is proven with a synthetic-conflict unit test since the shipped catalog has no real floors to trip it yet.

## Components

- app/main.py exposes FastAPI endpoints for evaluation, review lifecycle, and reporting; also best-effort mounts the optional LLM triage agent's router (see below) if it and `anthropic` are importable
- app/auth.py holds bearer-token verification and RBAC (`require_roles`), split out of app/main.py so router.py (repo root) can reuse it without a circular import
- app/engine.py loads rule catalogs and applies deterministic procurement evaluation logic
- app/models.py defines vendor-transaction, decision, and review schemas
- orchestrator.py/router.py/tools.py (repo root, optional) — a Claude-powered triage agent over the same API, gated behind the `anthropic` package and `ANTHROPIC_API_KEY`; never computes risk itself, only calls the real `/evaluate`. Not part of the AWS Lambda package. See README "LLM triage agent"
- app/storage.py is a thin backend dispatcher (`COMPLIANCE_STORAGE_BACKEND`, default `sqlite`) over app/storage_sqlite.py (local/dev/test) and app/storage_dynamodb.py (AWS); app/storage_common.py holds the deserialization logic both share
- data/rules contains versioned control metadata for the eight procurement controls
- examples contains vendor-transaction sample payloads for manual testing
- tests/test_api.py contains API tests for auth, workflow, metrics, and summary behavior — always against the SQLite backend, since the suite never sets COMPLIANCE_STORAGE_BACKEND
- infra/ is a CDK (Python) app deploying the same, unmodified application to AWS — see docs/aws_deployment.md

## Audit Trail and Traceability

- every evaluation stores evaluated_at timestamp metadata
- POST /evaluate persists a decision record by case_id
- decision and review updates append immutable history events with actor identity and event type
- GET /decisions and GET /decisions/{case_id} provide current-state lookup
- legacy rows are deserialized with backward-compatible defaults where new fields were added later

## Access Control and Reporting

- protected endpoints require bearer tokens with sub and role claims
- supported roles: employee, compliance_analyst, compliance_manager, auditor
- assignment is manager-only; start and submit actions require authenticated reviewer identity match
- optional key-id trust map via COMPLIANCE_AUTH_KEYS_JSON
- optional issuer and audience enforcement via COMPLIANCE_AUTH_ISSUER and COMPLIANCE_AUTH_AUDIENCE
- temporary migration fallback COMPLIANCE_ALLOW_INSECURE_HEADERS allows legacy headers when explicitly enabled

## Review Lifecycle

- GET /reviews/queue returns active review queue items
- GET /reviews/metrics returns queue volume and SLA-aging metrics
- GET /dashboard/summary returns a per-control decision breakdown, triggered-signal frequency, risk-band distribution, and the active review queue snapshot in one response
- POST /reviews/{case_id}/assign assigns a reviewer
- POST /reviews/{case_id}/start transitions to in_review
- POST /reviews/{case_id} records final reviewer adjudication
- POST /reviews/{case_id}/reopen creates a new cycle with explicit reopen reason
- GET /reviews/{case_id} returns stored review record for the case

## Current Validation Status

- verified: all eight procurement rule catalogs load via API endpoints, each with populated `policy_references`
- verified: deterministic transaction evaluation returns structured decision records
- verified: assignment, start, submit, and reopen lifecycle transitions persist correctly
- verified: append-only history captures decision and review lifecycle events
- verified: queue metrics include status counts, SLA breach counts, and risk-band segmentation
- verified: summary reporting includes totals, completed reviews, overrides, and reopen dimensions
- verified: dashboard summary aggregates decisions per control (including zero-traffic controls) and per triggered signal
- verified: escalation recipients are computed per risk band per control and aggregated on the dashboard by recipient group
- verified: bearer auth, issuer/audience checks, and key-id trust behavior are covered by tests
- verified: `/reports/summary` and `/reviews/{case_id}/reopen` — previously broken by a field-name mismatch and a missing enum member from the prior domain — now work and are covered by tests
- verified: part-time/temporary contract engagements without a completed classification assessment return insufficient_evidence; a possible-misclassification finding returns human_review_required; a confirmed-contractor finding still routes to review; a standard vendor engagement skips the scrutiny entirely
- verified: gifts/hospitality below the approval threshold auto-close; above it (or at any amount for a government official) require an on-file approval; an explicit denial returns blocked at CRITICAL risk
- verified: a transaction with no vendor payment-detail change skips scrutiny; a changed-but-unverified detail returns insufficient_evidence; a failed verification returns blocked; a verified change still routes to review
- verified: `validate_no_internal_policy_conflicts()` catches a synthetic looser-than-regulatory-floor trigger and passes a stricter/equal one

## Immediate Next Build Step

- add explicit event emissions for risk computation and escalation transitions
- extend summary outputs with median and p95 review turnaround metrics
- confirm the Integrity in Public Life Act's enactment status and real numeric regulatory floors (approval thresholds, part-time hours) where they exist
