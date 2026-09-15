# Vendor Due-Diligence Gate

This repository defines a practical framework for an Agentic AI system that gates vendor spend: purchase orders and vendor transactions are checked against spend-approval thresholds and vendor due-diligence screening requirements before they're allowed to proceed. The MVP detects missing or failed controls, routes ambiguous or high-risk cases to a human reviewer, and maintains an auditable record of every compliance decision and review outcome.

## Current status

This repository contains the design foundation and a FastAPI MVP with four procurement-focused compliance controls, severity-based risk escalation, review workflow support, queue metrics, role-based access control, append-only audit history, and a local SQLite audit trail.

It also includes workspace customization for Copilot:

- `AGENTS.md` defines always-on repository guidance for the compliance workflow.
- `.github/agents/compliance-agent.agent.md` adds a named `Compliance Agent` mode for this workspace.

## Contents

- `docs/architecture.md` - end-to-end architecture and reference implementation design
- `docs/mvp.md` - first MVP scope and build notes
- `app/` - FastAPI service and deterministic evaluation engine
- `data/rules/` - versioned rule catalogs for procurement controls
- `examples/` - sample vendor-transaction payloads
- `.github/agents/` - named Copilot agent definitions for this workspace

## Current MVP controls

- `PROC-SPEND-APPROVAL-001`: purchase-order spend at or above the approval threshold requires an on-file approval; spend at or above the dual-approval threshold requires two independent approvals
- `PROC-VENDOR-DUEDILIGENCE-001`: new vendors, high-risk vendors, and spend at or above the screening threshold require completed vendor due-diligence screening, including a sanctions/watchlist check
- `PROC-INTL-VENDOR-001`: vendors based in a designated high-risk jurisdiction (versioned country-code list in the rule catalog), or spend at or above the enhanced due-diligence threshold, require completed screening plus enhanced due-diligence sign-off (e.g. local counsel review)
- `PROC-VENDOR-COI-001`: a flagged potential conflict of interest between the requestor and the vendor requires formal disclosure and an explicit compliance clearance decision; a cleared conflict still routes to mandatory review rather than auto-closing
- severity-based escalation: transactions are classified into risk bands (LOW, MEDIUM, HIGH, CRITICAL) with corresponding escalation actions
- output: structured compliance decision record with severity scores, risk metadata, and review state

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the API with `uvicorn app.main:app --reload`.
4. Open `http://127.0.0.1:8000/docs` for the interactive API docs.

Protected endpoints require bearer authentication:

- `Authorization: Bearer <signed_token>`
- required token claims: `sub` (caller identifier) and `role` (`employee`, `compliance_analyst`, `compliance_manager`, or `auditor`)
- signing configuration: set `COMPLIANCE_AUTH_SECRET` (HS256) for single-key mode
- key rotation mode: set `COMPLIANCE_AUTH_KEYS_JSON` to a JSON map of key IDs to secrets
- optional trust constraints: set `COMPLIANCE_AUTH_ISSUER` and `COMPLIANCE_AUTH_AUDIENCE` to enforce issuer and audience claim validation

Temporary migration fallback:

- set `COMPLIANCE_ALLOW_INSECURE_HEADERS=true` to allow legacy `X-User-Id` and `X-User-Role` headers during transition

## Example endpoints

- `GET /health`
- `GET /rules`
- `GET /rules/current`
- `GET /rules/{control_id}`
- `POST /evaluate` - submit a vendor transaction for compliance evaluation
- `GET /decisions`
- `GET /decisions/{case_id}`
- `GET /reviews/queue` - active review cases requiring action
- `GET /reviews/metrics` - queue volume and aging metrics by risk band
- `GET /reports/summary` - governance summary of decisions, reviews, and risk-band distributions
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign` - assign reviewer
- `POST /reviews/{case_id}/start` - start review
- `POST /reviews/{case_id}` - submit review outcome
- `POST /reviews/{case_id}/reopen` - reopen case for additional review

## Validated behavior

- both procurement rule catalogs load through the API
- transaction risk is calculated based on spend amount, vendor risk level, new-vendor status, and prior flagged transactions
- missing required approval or vendor screening evidence returns `insufficient_evidence` and queues the case for review
- an explicit approval denial or failed sanctions/watchlist screening returns `blocked` at CRITICAL risk
- spend at or above the dual-approval threshold with only one approval on file returns `human_review_required`
- fully-evidenced transactions with elevated risk (e.g. a high-risk vendor) are `approved` but still routed to mandatory review
- review-required cases enter the active queue and support assignment and workflow transitions
- completed review cases can be reopened with explicit reopen reason tracking
- review queue metrics aggregate active cases by severity band and track SLA aging
- summary reporting includes severity-band distributions for governance oversight
- signed bearer token auth is enforced on protected endpoints with key-id support and optional legacy header fallback
- role-based access controls protect sensitive transaction and review data
- append-only decision and review history is preserved alongside current case state

## Next steps

- implement escalation notifications to Procurement, Legal, and Finance based on severity band
- develop dashboard reporting for review metrics and governance oversight
- decide whether the previous employee-conduct domain content (`docs/ethics_workflow.md` and related narrative docs) should be archived, ported to a separate deployment, or retired
