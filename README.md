# Vendor Due-Diligence Gate

A deterministic compliance engine that gates vendor spend: purchase orders and vendor transactions are checked against a versioned rule catalog before they're allowed to proceed. Every decision is explainable, cites the regulation or internal policy behind it, and leaves a permanent audit trail.

See [docs/problem_statement.md](docs/problem_statement.md) for who this is for and why it exists.

## Features

- **8 compliance controls** covering spend approval, vendor due diligence, jurisdiction/sanctions risk, conflict of interest, expense receipts, worker classification, gifts & hospitality (anti-bribery), and vendor payment-change verification (see [Compliance controls](#compliance-controls) below)
- **Deterministic risk scoring** — every transaction is evaluated against explicit, versioned thresholds, producing a risk band (low/medium/high/critical) and a decision (`approved`, `blocked`, `insufficient_evidence`, or `human_review_required`)
- **Human-in-the-loop review** — high-risk or ambiguous cases route to a review queue with assignment, start/submit, and reopen workflows
- **Policy traceability** — every control cites the regulation or internal policy it enforces
- **Escalation routing** — each decision computes which stakeholder groups (Procurement/Legal/Finance) should be notified, from a versioned per-control policy
- **Governance dashboard** — per-control decision breakdown, risk-signal frequency, and pending-notification counts in a single call
- **Append-only audit trail** — every decision and review action is logged immutably
- **Role-based access control** — four roles (`employee`, `compliance_analyst`, `compliance_manager`, `auditor`), enforced on every protected endpoint
- **Deploys to AWS unchanged** — the same code runs on Lambda, API Gateway, DynamoDB, Cognito, and S3 via the CDK app in `infra/`
- **Optional LLM triage agent** — a Claude-powered assistant that extracts structured fields from a plain-English transaction description and calls the same deterministic engine

## Architecture

A FastAPI service (`app/`) built around a deterministic rule engine (`app/engine.py`) that reads versioned JSON rule catalogs (`data/rules/`). Storage is backend-agnostic (`app/storage.py`) — SQLite locally, DynamoDB in AWS — selected by an environment variable, with no code changes required. See [docs/architecture.md](docs/architecture.md) for the full design.

## Getting started

### Prerequisites

- Python 3.11+

### Install

```bash
pip install -r requirements.txt
```

### Run locally

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API docs.

For quick manual testing without minting a JWT, run `python dev_server.py` instead — it sets `COMPLIANCE_ALLOW_INSECURE_HEADERS=true` so protected endpoints accept plain `X-User-Id`/`X-User-Role` headers.

### Authentication

Protected endpoints require bearer authentication:

| Variable | Purpose |
|---|---|
| `COMPLIANCE_AUTH_SECRET` | HS256 shared secret (single-key mode) |
| `COMPLIANCE_AUTH_KEYS_JSON` | Key-ID → secret map, for key rotation |
| `COMPLIANCE_AUTH_ISSUER` / `COMPLIANCE_AUTH_AUDIENCE` | Optional issuer/audience validation |
| `COMPLIANCE_AUTH_JWKS_URL` | RS256/JWKS verification (used in AWS, against Cognito) |
| `COMPLIANCE_ALLOW_INSECURE_HEADERS` | Accept plain `X-User-Id`/`X-User-Role` headers — local dev only |

A token needs `sub` (caller ID) and `role` claims (or, for Cognito, a `cognito:groups` claim matching one of the four roles).

### Run on AWS

The same application code deploys unchanged via the CDK app in `infra/`:

```bash
cd infra
pip install -r requirements.txt
cdk bootstrap aws://<account-id>/<region>
cdk deploy --all
```

See [docs/aws_deployment.md](docs/aws_deployment.md) for what gets built, the auth model, and full details.

### Run tests

```bash
python -m pytest tests/test_api.py
```

## API reference

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /rules` | List all rule catalogs |
| `GET /rules/current` | Get the default control's rule |
| `GET /rules/{control_id}` | Get a specific control's rule |
| `POST /evaluate` | Submit a vendor transaction for evaluation |
| `GET /decisions` | List all decisions |
| `GET /decisions/{case_id}` | Get a decision by case ID |
| `GET /reviews/queue` | Active review queue |
| `GET /reviews/metrics` | Queue volume and aging metrics |
| `GET /reviews/{case_id}` | Get a case's review record |
| `POST /reviews/{case_id}/assign` | Assign a reviewer |
| `POST /reviews/{case_id}/start` | Start a review |
| `POST /reviews/{case_id}` | Submit a review outcome |
| `POST /reviews/{case_id}/reopen` | Reopen a completed review |
| `GET /reports/summary` | Governance summary report |
| `GET /dashboard/summary` | Per-control and per-signal dashboard |
| `POST /agent/triage` | Optional LLM triage agent (see below) |

## Compliance controls

| Control | What it checks |
|---|---|
| `PROC-SPEND-APPROVAL-001` | Spend-approval thresholds; dual approval above a higher threshold |
| `PROC-VENDOR-DUEDILIGENCE-001` | Vendor due-diligence / sanctions screening for new or high-risk vendors |
| `PROC-INTL-VENDOR-001` | Enhanced due diligence for vendors in high-risk jurisdictions |
| `PROC-VENDOR-COI-001` | Conflict-of-interest disclosure and compliance clearance |
| `PROC-EXPENSE-RECEIPT-001` | Itemized receipt documentation and amount reconciliation |
| `PROC-PART-TIME-CONTRACT-001` | Worker-classification risk for part-time/temporary vendor engagements |
| `PROC-GIFTS-HOSPITALITY-001` | Gifts/hospitality/entertainment pre-approval (anti-bribery) |
| `PROC-VENDOR-PAYMENT-CHANGE-001` | Independent verification of vendor payment/banking detail changes |

Every control's rule catalog (`data/rules/*.json`) carries a `policy_references` list citing the regulation or internal policy it enforces — see [docs/mvp.md](docs/mvp.md#regulatory-sourcing-and-the-internal-policy-layer-barbadoscaribbean-for-now) for the full citation list and how internal thresholds are checked against any confirmed regulatory floor.

## LLM triage agent (optional)

`orchestrator.py`, `router.py`, and `tools.py` add an optional Claude-powered triage agent at `POST /agent/triage`: submit a raw, plain-English transaction description and get back structured triage. It never computes or states risk itself — every decision comes from a real call to `POST /evaluate`.

```bash
export ANTHROPIC_API_KEY=<your key>
```

It's fully optional: `app/main.py` mounts it only if `router.py` and the `anthropic` package are importable, so the core app — including the AWS Lambda deployment, which excludes this scaffolding — works identically without it.

## Project structure

```
app/                                   FastAPI service, rule engine, models, storage, auth
data/rules/                            Versioned rule catalogs (one JSON file per control)
examples/                              Sample vendor-transaction payloads
infra/                                 CDK app for AWS deployment
tests/                                 API test suite
docs/                                  Design docs
orchestrator.py, router.py, tools.py   Optional LLM triage agent
dev_server.py                          Local dev server with insecure-header auth
lambda_handler.py                      AWS Lambda entry point
AGENTS.md, .github/agents/             Copilot workspace agent configuration
```

## Documentation

- [docs/problem_statement.md](docs/problem_statement.md) — who has the problem and why
- [docs/architecture.md](docs/architecture.md) — end-to-end design
- [docs/mvp.md](docs/mvp.md) — MVP scope, components, and regulatory sourcing
- [docs/aws_deployment.md](docs/aws_deployment.md) — AWS deployment details
- [CHANGELOG.md](CHANGELOG.md) — build history and what's been verified along the way

## Roadmap

- Run `cdk deploy` against a real AWS account and provision a first `compliance_manager` user
- Wire `escalation_recipients` to an actual outbound channel (email/Slack)
- Confirm the status of the Integrity in Public Life Act for `PROC-VENDOR-COI-001`
- Extend regulatory sourcing beyond Barbados/Caribbean as the vendor base grows
- Confirm real numeric regulatory floors where they exist, for `validate_no_internal_policy_conflicts()` to enforce
- Decide the fate of `docs/`'s older employee-conduct-domain narrative docs (`ethics_workflow.md` and similar) — retired along with that domain but never removed
