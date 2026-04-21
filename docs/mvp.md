# MVP Scope

This MVP implements a narrow but realistic Ethics and Compliance workflow for gifts, meals, entertainment, and travel with a shared deterministic evaluation and human review pattern.

## Selected Recurring Process For The Assignment

The recurring process selected for the next phase of the project is vendor invoice review.

- business activity: accounts payable and procurement teams process a high volume of vendor invoices
- compliance problem: invoices must be checked for accuracy, fraud indicators, and adherence to procurement controls
- agent role: monitor invoice submissions, triage exceptions, and summarize flagged cases for compliance or finance review

Typical issues the agent would watch for include:

- invoice amount does not match the purchase order or goods receipt
- duplicate invoice numbers or repeated invoice amounts from the same vendor
- missing approval or approval from the wrong authority
- invoice submitted outside agreed payment terms or procurement workflow
- suspicious vendor behavior that may indicate fraud or policy circumvention

## Use Case

- Trigger: an employee submits a gifts or hospitality request or a reimbursement case for review
- Policy 1: submissions at or above the pre-approval threshold require approval from a compliance manager
- Policy 2: submissions at or above the evidence threshold require a receipt or invoice reference
- Outcomes: compliant, non-compliant, insufficient evidence, or human review required

## Components

- `app/main.py` exposes API endpoints
- `app/engine.py` loads the rule catalog, selects the control by `control_id`, and evaluates the case deterministically
- `app/models.py` defines the request and response schema
- `app/storage.py` persists decision records in a local SQLite audit store
- `data/rules/approval_thresholds.json` stores the gifts-and-hospitality pre-approval control metadata
- `data/rules/expense_receipts.json` stores the gifts-and-hospitality evidence control metadata
- `examples/` contains sample payloads for manual testing

## Audit Trail

- every evaluation returns an `evaluated_at` timestamp
- every `POST /evaluate` call persists or updates a decision record by `case_id`
- `GET /decisions` lists all stored decision records
- `GET /decisions/{case_id}` returns one stored record for audit lookup
- persisted decisions remain readable even when older audit rows predate newer rule metadata fields
- completed human reviews update the stored decision record with the final disposition

## Human Review Workflow

- `GET /reviews/queue` returns active review cases that still need analyst resolution
- `GET /reviews/metrics` returns queue volume and aging metrics for active review cases
- `POST /reviews/{case_id}/assign` assigns a reviewer and marks the case as assigned
- `POST /reviews/{case_id}/start` marks an assigned case as in review
- `POST /reviews/{case_id}` records an analyst decision, final compliance state, and notes
- `GET /reviews/{case_id}` returns the stored reviewer action for audit lookup
- reviewer outcomes support approval, rejection, and explicit override capture

## Why This Is a Real Ethics and Compliance Use Case

- gifts and hospitality is a common anti-bribery and conflict-of-interest workflow handled by compliance teams
- the workflow combines clear thresholds with ambiguous exceptions, which makes it a good fit for an agentic pattern
- the required controls are easy to explain to stakeholders: who approved, what was spent, what evidence exists, and whether escalation is needed
- the human review queue reflects how compliance analysts already work in practice

## Validation Status

- verified: both control catalogs load through the API
- verified: gifts-and-hospitality approval and receipt examples evaluate with the expected decisions
- verified: queue, assignment, start, and review completion flows work end to end
- verified: queue metrics load successfully after adding backward-compatible deserialization for legacy audit rows

## Immediate Next Build Step

- add automated tests for `/evaluate`, `/reviews/queue`, `/reviews/metrics`, and the review lifecycle
- decide how reopened cases should interact with prior review records in the audit store
- add recipient and context risk signals such as government official status, country, and event purpose
