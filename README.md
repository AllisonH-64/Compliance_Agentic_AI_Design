# Employee Conduct Compliance Agentic AI

This repository defines a practical framework for an Agentic AI system supporting employee conduct and workplace compliance: harassment, discrimination, client treatment, and international employment governance. The MVP detects policy violations, routes incidents to investigators based on severity, and maintains an auditable record of all compliance decisions and review outcomes.

## Current status

This repository now contains the design foundation and a FastAPI MVP with four conduct-focused compliance controls, severity-based risk escalation, investigation workflow support, queue metrics, role-based access control, append-only audit history, and a local SQLite audit trail.

It also includes workspace customization for Copilot:

- `AGENTS.md` defines always-on repository guidance for the compliance workflow.
- `.github/agents/compliance-agent.agent.md` adds a named `Compliance Agent` mode for this workspace.

## Contents

- `docs/architecture.md` - end-to-end architecture and reference implementation design
- `docs/ethics_workflow.md` - conduct and employee governance compliance workflow
- `docs/mvp.md` - first MVP scope and build notes
- `docs/risk_signals_and_escalation_rules.md` - escalation logic and investigation lifecycle
- `docs/governance_operating_model.md` - governance ownership and assurance cadence
- `app/` - FastAPI service and deterministic evaluation engine
- `data/rules/` - versioned rule catalogs for conduct controls
- `examples/` - sample incident report payloads
- `.github/agents/` - named Copilot agent definitions for this workspace

## Current MVP controls

- `CONDUCT-HARASSMENT-001`: harassment and bullying incidents requiring severity assessment and mandatory investigation for medium/high-risk cases
- `CONDUCT-DISCRIMINATION-001`: discrimination allegations involving protected characteristics require immediate escalation to HR and Legal
- `CONDUCT-CLIENT-001`: client treatment and confidentiality breaches evaluated for business impact and reputation risk
- `CONDUCT-INTL-GOV-001`: international employment law and regulatory compliance issues with jurisdiction-specific escalation
- severity-based escalation: incidents are classified into risk bands (LOW, MEDIUM, HIGH, CRITICAL) with corresponding escalation actions
- output: structured compliance decision record with severity scores, investigation recommendations, risk metadata, and review state

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
- `POST /evaluate` - submit an incident for compliance evaluation
- `GET /decisions`
- `GET /decisions/{case_id}`
- `GET /investigations/queue` - active investigation cases requiring action
- `GET /investigations/metrics` - queue volume and aging metrics by risk band
- `GET /reports/summary` - governance summary of decisions, investigations, and risk-band distributions
- `GET /reviews/{case_id}`
- `POST /reviews/{case_id}/assign` - assign investigator
- `POST /reviews/{case_id}/start` - start investigation
- `POST /reviews/{case_id}` - submit investigation outcome
- `POST /reviews/{case_id}/reopen` - reopen case for additional investigation

## Validated behavior

- all four conduct rule catalogs load through the API
- incident severity is calculated based on description length, protected characteristics, prior complaints, and involved party count
- discrimination and international governance incidents automatically escalate to CRITICAL severity with mandatory investigation
- harassment and client treatment incidents route to investigation based on computed severity bands
- high-severity cases (HIGH/CRITICAL) require immediate investigation escalation to appropriate stakeholders
- investigation-required cases enter the active queue and support assignment and workflow transitions
- completed investigation cases can be reopened with explicit reopen reason tracking
- investigation queue metrics aggregate active cases by severity band and track SLA aging
- summary reporting includes severity-band distributions for governance oversight
- signed bearer token auth is enforced on protected endpoints with key-id support and optional legacy header fallback
- role-based access controls protect sensitive incident and investigation data
- append-only decision and investigation history is preserved alongside current case state

## Next steps

- extend investigation workflow with formal investigation notes and evidence chain tracking
- add jurisdiction-specific investigation protocols based on country code and regulatory requirements
- implement escalation notifications to Legal, HR, and Management based on severity band
- develop dashboard reporting for investigation metrics and governance oversight
