# MVP Scope

This MVP implements one compliance workflow for approval-threshold checks.

## Use Case

- Trigger: a transaction is submitted for review
- Policy: transactions at or above the approval threshold require approval from the finance director
- Outcomes: compliant, non-compliant, insufficient evidence, or human review required

## Components

- `app/main.py` exposes API endpoints
- `app/engine.py` evaluates a transaction case against the current rule catalog
- `app/models.py` defines the request and response schema
- `app/storage.py` persists decision records in a local SQLite audit store
- `data/rules/approval_thresholds.json` stores the current control metadata
- `examples/` contains sample payloads for manual testing

## Audit Trail

- every evaluation returns an `evaluated_at` timestamp
- every `POST /evaluate` call persists or updates a decision record by `case_id`
- `GET /decisions` lists all stored decision records
- `GET /decisions/{case_id}` returns one stored record for audit lookup
- completed human reviews update the stored decision record with the final disposition

## Human Review Workflow

- `GET /reviews/queue` returns active review cases that still need analyst resolution
- `POST /reviews/{case_id}/assign` assigns a reviewer and marks the case as assigned
- `POST /reviews/{case_id}/start` marks an assigned case as in review
- `POST /reviews/{case_id}` records an analyst decision, final compliance state, and notes
- `GET /reviews/{case_id}` returns the stored reviewer action for audit lookup
- reviewer outcomes support approval, rejection, and explicit override capture

## Immediate Next Build Step

- add a second rule and a rule selection layer
- add reviewer SLA tracking and aging metrics
- add a second control domain with distinct evidence requirements
