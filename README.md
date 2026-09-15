# Vendor Due-Diligence Gate

This repository defines a practical framework for an Agentic AI system that gates vendor spend: purchase orders and vendor transactions are checked against spend-approval thresholds and vendor due-diligence screening requirements before they're allowed to proceed. The MVP detects missing or failed controls, routes ambiguous or high-risk cases to a human reviewer, and maintains an auditable record of every compliance decision and review outcome.

## Current status

This repository contains the design foundation and a FastAPI MVP with seven procurement-focused compliance controls, severity-based risk escalation, review workflow support, queue metrics, role-based access control, append-only audit history, and a local SQLite audit trail.

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
- `PROC-EXPENSE-RECEIPT-001`: expenses at or above the receipt threshold require an attached itemized receipt; a receipt total that doesn't reconcile with the claimed amount within tolerance routes to human review
- `PROC-PART-TIME-CONTRACT-001`: vendor engagements structured as part-time contract or temporary staffing require a completed worker-classification risk assessment; an assessment suggesting the engagement functions as employment routes to human review rather than an outright block, since the fix is reclassification, not refusal — a confirmed-compliant engagement still routes to review given the elevated baseline risk of this engagement type
- `PROC-GIFTS-HOSPITALITY-001`: gifts, hospitality, or entertainment given to or received from a vendor require pre-approval above a threshold; any amount involving a government official requires pre-approval regardless of size, reflecting the heightened bribery/corruption risk and criminal liability of public-official gifts
- severity-based escalation: transactions are classified into risk bands (LOW, MEDIUM, HIGH, CRITICAL) with corresponding escalation actions
- escalation notifications: each control has a versioned, risk-band-driven policy (in its rule catalog) for which stakeholder groups (Procurement, Legal, Finance) to notify; a decision's `escalation_recipients` field is computed from that policy rather than hardcoded
- policy traceability: every control's rule catalog carries a `policy_references` list citing the external regulation/standard it maps to (where one was confirmed) and/or the company's own internal policy — see "Regulatory sourcing" below
- output: structured compliance decision record with severity scores, risk metadata, escalation recipients, and review state

## Regulatory sourcing (Barbados/Caribbean, for now)

Each control's `data/rules/*.json` catalog carries a `policy_references` list, tagged `external_regulation` or `internal_policy`, so every rule evaluation maps back to something citable rather than an invented label. This was researched, not assumed — real sources found:

- **Barbados Public Procurement Act, 2021 (Act No. 30 of 2021)** and the **CARICOM Protocol on Procurement** — `PROC-SPEND-APPROVAL-001`, `PROC-INTL-VENDOR-001`
- **Money Laundering and Financing of Terrorism (Prevention and Control) Act, 2011-23** and **CFATF** (Caribbean Financial Action Task Force) FATF-Recommendations compliance — `PROC-VENDOR-DUEDILIGENCE-001`, `PROC-INTL-VENDOR-001`
- **Employment Rights Act, 2012 (Act 2012-9)** — `PROC-PART-TIME-CONTRACT-001`
- **Prevention of Corruption Act, 2021 (Barbados)** — `PROC-GIFTS-HOSPITALITY-001`; covers bribery/gifts to both public officials and private-sector counterparties, with real criminal penalties (up to BBD$1,500,000 or 15 years on indictment) and corporate liability

Two honesty gaps, left as gaps rather than papered over: no confirmed, currently-enacted Barbados private-sector conflict-of-interest statute was found (the Integrity in Public Life Bill failed in the Senate in 2020 and was reintroduced in 2023, but I found no confirmation of Senate passage or entry into force, so it isn't cited), so `PROC-VENDOR-COI-001` is internal-policy-only; and no dedicated Barbados receipt-documentation statute was found, so `PROC-EXPENSE-RECEIPT-001` is internal-policy-only too. Neither of these should be read as "no regulation exists" — only that this pass didn't confirm one.

None of the researched sources gave a verified numeric threshold (a specific dollar approval amount, a specific part-time-hours cutoff), so every threshold in `escalation_triggers` remains an internal-policy value — nothing here should be read as a legally-mandated number.

`app/engine.py`'s `validate_no_internal_policy_conflicts()` is the enforcement point for internal rules living alongside a regulation: a `PolicyReference` can declare `minimum_threshold_field`/`minimum_threshold_value` when a real regulatory floor is confirmed for one of a control's trigger keys, and `load_rules()` refuses to load any catalog whose internal trigger value is looser than that floor. It's currently a no-op against the shipped catalogs (no numeric floors have been confirmed yet) but is exercised directly in `tests/test_api.py` against a synthetic conflicting rule.

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
- `GET /dashboard/summary` - per-control decision breakdown, triggered-signal frequency, risk-band distribution, and the active review queue snapshot in a single response
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign` - assign reviewer
- `POST /reviews/{case_id}/start` - start review
- `POST /reviews/{case_id}` - submit review outcome
- `POST /reviews/{case_id}/reopen` - reopen case for additional review

## Validated behavior

- all seven procurement rule catalogs load through the API, each with populated `policy_references`
- transaction risk is calculated based on spend amount, vendor risk level, new-vendor status, and prior flagged transactions
- missing required approval or vendor screening evidence returns `insufficient_evidence` and queues the case for review
- an explicit approval denial or failed sanctions/watchlist screening returns `blocked` at CRITICAL risk
- spend at or above the dual-approval threshold with only one approval on file returns `human_review_required`
- fully-evidenced transactions with elevated risk (e.g. a high-risk vendor) are `approved` but still routed to mandatory review
- review-required cases enter the active queue and support assignment and workflow transitions
- completed review cases can be reopened with explicit reopen reason tracking
- review queue metrics aggregate active cases by severity band and track SLA aging
- summary reporting includes severity-band distributions for governance oversight
- the dashboard summary breaks decisions down per control (including controls with zero traffic) and surfaces the most frequently triggered risk signals
- escalation recipients (Procurement, Legal, Finance) are computed per decision from each control's versioned, risk-band notification policy, and the dashboard aggregates pending notification counts by recipient group
- a part-time/temporary contract vendor engagement without a completed worker-classification assessment returns `insufficient_evidence`; an assessment suggesting the engagement resembles employment returns `human_review_required` rather than a block; a standard vendor engagement skips this scrutiny entirely
- a gift/hospitality/entertainment transaction below the approval threshold auto-closes; above it (or at any amount for a government-official counterparty) it requires an on-file approval, and an explicit denial returns `blocked` at CRITICAL risk
- `validate_no_internal_policy_conflicts()` blocks catalog loading if an internal trigger value is ever looser than a declared regulatory floor
- signed bearer token auth is enforced on protected endpoints with key-id support and optional legacy header fallback
- role-based access controls protect sensitive transaction and review data
- append-only decision and review history is preserved alongside current case state

## Next steps

- wire `escalation_recipients` to an actual outbound channel (email/Slack) once real distribution lists exist; today it's a computed, auditable field rather than a sent notification
- confirm the status of the Integrity in Public Life Act and, if enacted, add it as `PROC-VENDOR-COI-001`'s external regulation reference
- extend regulatory sourcing beyond Barbados/Caribbean to other jurisdictions as the vendor base grows
- confirm real numeric regulatory floors (approval-dollar thresholds, part-time-hours definitions) where they exist, so `validate_no_internal_policy_conflicts()` has something concrete to enforce
- decide whether the previous employee-conduct domain content (`docs/ethics_workflow.md` and related narrative docs) should be archived, ported to a separate deployment, or retired
