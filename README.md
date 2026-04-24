# Compliance Agentic AI Design

This repository defines a practical concept for an Agentic AI system that supports a real Ethics and Compliance workflow: gifts, meals, entertainment, and travel review. The MVP detects policy breaches, routes ambiguous or high-risk cases to a human analyst, and preserves a defensible audit trail.

## Current status

This repository now contains the design baseline and a FastAPI MVP with two deterministic gifts-and-hospitality controls, contextual risk-signal escalation, human review workflow support, review queue metrics, simple role-based access control, append-only audit history, and a local SQLite audit trail.

## Contents

- `docs/architecture.md` - end-to-end architecture and reference implementation design
- `docs/ethics_workflow.md` - concrete project concept for a gifts and hospitality compliance workflow
- `docs/mvp.md` - first MVP scope and build notes
- `docs/risk_signals_and_escalation_rules.md` - next-step design for contextual risk signals, escalation logic, and reopened-case lifecycle
- `docs/governance_operating_model.md` - governance ownership, traceability, KPI thresholds, and assurance cadence
- `app/` - FastAPI service and deterministic evaluation engine
- `data/rules/` - versioned rule catalogs for the active controls
- `examples/` - sample request payloads

## Current MVP controls

- `ETH-GIFT-001`: gifts or hospitality spend at or above 150 USD require pre-approval from `compliance_manager`
- `ETH-GIFT-002`: gifts or hospitality spend at or above 75 USD require receipt evidence in USD scope
- contextual escalation: compliant baseline outcomes can still be routed to mandatory human review when high-risk signals are present
- output: structured compliance decision record with severity, confidence, risk metadata, recommended action, and review state

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the API with `uvicorn app.main:app --reload`.
4. Open `http://127.0.0.1:8000/docs` for the interactive API docs.

Protected endpoints require bearer authentication:

- `Authorization: Bearer <signed_token>`
- required token claims: `sub` (caller identifier) and `role` (`employee`, `compliance_analyst`, `compliance_manager`, or `auditor`)
- signing configuration: set `COMPLIANCE_AUTH_SECRET` (HS256) for single-key mode
- key rotation mode: set `COMPLIANCE_AUTH_KEYS_JSON` to a JSON map of key IDs to secrets (for example `{"key-1":"...","key-2":"..."}`), and include `kid` in token headers
- optional trust constraints: set `COMPLIANCE_AUTH_ISSUER` and `COMPLIANCE_AUTH_AUDIENCE` to enforce issuer and audience claim validation

Temporary migration fallback:

- set `COMPLIANCE_ALLOW_INSECURE_HEADERS=true` to allow legacy `X-User-Id` and `X-User-Role` headers during transition

## Example endpoints

- `GET /health`
- `GET /rules`
- `GET /rules/current`
- `GET /rules/{control_id}`
- `POST /evaluate`
- `GET /decisions`
- `GET /decisions/{case_id}`
- `GET /reviews/queue` - active review cases
- `GET /reviews/metrics` - queue volume and SLA-style aging metrics, including risk-band segmentation
- `GET /reports/summary` - management summary of decisions, reviews, overrides, reopen counts, and risk-band distributions
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign`
- `POST /reviews/{case_id}/start`
- `POST /reviews/{case_id}`
- `POST /reviews/{case_id}/reopen`

Reviewer submissions now set the final case decision and close the review requirement on the stored decision record.

## Validated behavior

- both rule catalogs load through the API
- gifts-and-hospitality approval and receipt cases evaluate correctly with the sample payload shapes
- risk-signal fields are accepted on case input and produce risk metadata (`risk_band`, `risk_score`, `triggered_signal_ids`, `escalation_decision`)
- high-risk contextual signals (for example government-official involvement) escalate otherwise compliant cases to mandatory human review
- review-required cases enter the queue, support assignment and in-review transitions, and persist the final reviewer disposition
- completed review cases can be reopened into a new review cycle with explicit reopen reason capture
- review queue metrics aggregate active review cases from the persisted audit store and segment queue/SLA counts by risk band
- summary reporting includes risk-band distributions and reopened-case totals for governance monitoring
- signed bearer token auth is enforced by default on protected endpoints with key-id trust support, optional issuer/audience validation, and optional transition fallback for legacy headers
- role-based access checks protect sensitive decision and review endpoints
- append-only decision and review history is preserved alongside the latest case state
- automated API tests cover auth, review lifecycle, audit history, and summary reporting

## Next steps

- implement the design in `docs/risk_signals_and_escalation_rules.md` by adding contextual risk signals and escalation routing on top of deterministic controls
- refine reopened-case semantics further with explicit cycle-level review records
- migrate HS256 shared-secret verification to asymmetric keys with JWKS distribution for production trust boundaries
