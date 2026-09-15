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

## Decision Outcomes

- approved
- blocked
- insufficient_evidence
- human_review_required

## Components

- app/main.py exposes FastAPI endpoints for evaluation, review lifecycle, and reporting
- app/engine.py loads rule catalogs and applies deterministic procurement evaluation logic
- app/models.py defines vendor-transaction, decision, and review schemas
- app/storage.py persists current records plus append-only decision and review history
- data/rules contains versioned control metadata for the five procurement controls
- examples contains vendor-transaction sample payloads for manual testing
- tests/test_api.py contains API tests for auth, workflow, metrics, and summary behavior

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
- POST /reviews/{case_id}/assign assigns a reviewer
- POST /reviews/{case_id}/start transitions to in_review
- POST /reviews/{case_id} records final reviewer adjudication
- POST /reviews/{case_id}/reopen creates a new cycle with explicit reopen reason
- GET /reviews/{case_id} returns stored review record for the case

## Current Validation Status

- verified: all five procurement rule catalogs load via API endpoints
- verified: deterministic transaction evaluation returns structured decision records
- verified: assignment, start, submit, and reopen lifecycle transitions persist correctly
- verified: append-only history captures decision and review lifecycle events
- verified: queue metrics include status counts, SLA breach counts, and risk-band segmentation
- verified: summary reporting includes totals, completed reviews, overrides, and reopen dimensions
- verified: bearer auth, issuer/audience checks, and key-id trust behavior are covered by tests
- verified: `/reports/summary` and `/reviews/{case_id}/reopen` — previously broken by a field-name mismatch and a missing enum member from the prior domain — now work and are covered by tests

## Immediate Next Build Step

- add explicit event emissions for risk computation and escalation transitions
- extend summary outputs with median and p95 review turnaround metrics
- decide the fate of the retired employee-conduct rule catalogs and narrative docs (archive vs. separate deployment)
