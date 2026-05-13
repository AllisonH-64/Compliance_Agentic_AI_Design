# MVP Scope

This MVP implements an employee conduct compliance workflow with deterministic rule evaluation, risk-banded escalation, human investigation routing, and auditable lifecycle tracking.

## Current Program Scope

The implemented program focuses on employee-conduct incidents rather than spend approvals.

- business activity: intake and triage of workplace conduct incidents
- compliance problem: incidents require consistent policy application, severity classification, and accountable escalation
- agent role: evaluate incident submissions, route investigations, and maintain a complete audit trail

## In-Scope Controls

- CONDUCT-HARASSMENT-001: harassment and bullying incident handling
- CONDUCT-DISCRIMINATION-001: discrimination allegations and protected-characteristic sensitivity
- CONDUCT-CLIENT-001: client treatment and relationship conduct concerns
- CONDUCT-INTL-GOV-001: international governance and jurisdiction-sensitive conduct concerns

## Decision Outcomes

- policy_violation_confirmed
- cleared
- insufficient_evidence
- investigation_required

## Components

- app/main.py exposes FastAPI endpoints for evaluation, investigation lifecycle, and reporting
- app/engine.py loads rule catalogs and applies deterministic conduct evaluation logic
- app/models.py defines incident, decision, and review schemas
- app/storage.py persists current records plus append-only decision and review history
- data/rules contains versioned control metadata for the four conduct controls
- examples contains conduct-focused sample payloads for manual testing
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

## Investigation Lifecycle

- GET /reviews/queue returns active investigation queue items
- GET /reviews/metrics returns queue volume and SLA-aging metrics
- POST /reviews/{case_id}/assign assigns a reviewer
- POST /reviews/{case_id}/start transitions to in_review
- POST /reviews/{case_id} records final reviewer adjudication
- POST /reviews/{case_id}/reopen creates a new cycle with explicit reopen reason
- GET /reviews/{case_id} returns stored review record for the case

## Current Validation Status

- verified: all conduct rule catalogs load via API endpoints
- verified: deterministic incident evaluation returns structured decision records
- verified: assignment, start, submit, and reopen lifecycle transitions persist correctly
- verified: append-only history captures decision and review lifecycle events
- verified: queue metrics include status counts, SLA breach counts, and risk-band segmentation
- verified: summary reporting includes totals, completed investigations, overrides, and reopen dimensions
- verified: bearer auth, issuer/audience checks, and key-id trust behavior are covered by tests

## Immediate Next Build Step

- align remaining legacy gift-domain tests and references to the conduct-domain schema
- add explicit event emissions for risk computation and escalation transitions
- extend summary outputs with median and p95 investigation turnaround metrics
