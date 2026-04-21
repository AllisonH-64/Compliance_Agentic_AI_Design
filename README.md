# Compliance Agentic AI Design

This repository defines a practical concept for an Agentic AI system that supports a real Ethics and Compliance workflow: gifts, meals, entertainment, and travel review. The MVP detects policy breaches, routes ambiguous or high-risk cases to a human analyst, and preserves a defensible audit trail.

## Current status

This repository now contains the design baseline and a FastAPI MVP with two deterministic gifts-and-hospitality controls, human review workflow support, review queue metrics, and a local SQLite audit trail.

## Contents

- `docs/architecture.md` - end-to-end architecture and reference implementation design
- `docs/ethics_workflow.md` - concrete project concept for a gifts and hospitality compliance workflow
- `docs/mvp.md` - first MVP scope and build notes
- `app/` - FastAPI service and deterministic evaluation engine
- `data/rules/` - versioned rule catalogs for the active controls
- `examples/` - sample request payloads

## Current MVP controls

- `ETH-GIFT-001`: gifts or hospitality spend at or above 150 USD require pre-approval from `compliance_manager`
- `ETH-GIFT-002`: gifts or hospitality spend at or above 75 USD require receipt evidence in USD scope
- output: structured compliance decision record with severity, confidence, recommended action, and review state

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the API with `uvicorn app.main:app --reload`.
4. Open `http://127.0.0.1:8000/docs` for the interactive API docs.

## Example endpoints

- `GET /health`
- `GET /rules`
- `GET /rules/current`
- `GET /rules/{control_id}`
- `POST /evaluate`
- `GET /decisions`
- `GET /decisions/{case_id}`
- `GET /reviews/queue` - active review cases
- `GET /reviews/metrics` - queue volume and SLA-style aging metrics
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign`
- `POST /reviews/{case_id}/start`
- `POST /reviews/{case_id}`

Reviewer submissions now set the final case decision and close the review requirement on the stored decision record.

## Validated behavior

- both rule catalogs load through the API
- gifts-and-hospitality approval and receipt cases evaluate correctly with the sample payload shapes
- review-required cases enter the queue, support assignment and in-review transitions, and persist the final reviewer disposition
- review queue metrics aggregate active review cases from the persisted audit store

## Next steps

- add automated API tests for both controls and the review lifecycle
- extend the workflow with recipient-risk factors such as government official involvement, geography, and repeat interactions
- refine queue semantics for reopened cases and older audit records
