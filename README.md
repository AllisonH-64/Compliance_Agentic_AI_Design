# Compliance Agentic AI Design

This repository contains the initial architecture and solution design for an agentic system that detects compliance problems, routes high-risk cases for human review, and maintains a defensible audit trail.

## Current status

This repository now contains the design baseline and an initial FastAPI MVP for one approval-threshold compliance workflow.

## Contents

- `docs/architecture.md` - end-to-end architecture and reference implementation design
- `docs/mvp.md` - first MVP scope and build notes
- `app/` - FastAPI service and deterministic evaluation engine
- `data/rules/` - versioned rule catalog for the first control
- `examples/` - sample request payloads

## First MVP use case

- control: large transaction approval compliance
- rule: transactions at or above 10000 USD require approval from `finance_director`
- output: structured compliance decision record with severity, confidence, and recommended action

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the API with `uvicorn app.main:app --reload`.
4. Open `http://127.0.0.1:8000/docs` for the interactive API docs.

## Example endpoints

- `GET /health`
- `GET /rules/current`
- `POST /evaluate`
- `GET /decisions`
- `GET /decisions/{case_id}`
- `GET /reviews/queue` - active review cases
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign`
- `POST /reviews/{case_id}/start`
- `POST /reviews/{case_id}`

Reviewer submissions now set the final case decision and close the review requirement on the stored decision record.

## Next steps

- support multiple rule catalogs and control domains
- update decision state after reviewer adjudication
- add reviewer assignment and status tracking
