# Compliance Agentic AI - Slide Summary

## Slide 1: Title

Compliance Agentic AI for Employee Conduct

- Fast, consistent incident triage
- Human accountability for final decisions
- Full audit trail for governance

## Slide 2: The Problem

Compliance teams process many conduct incidents.

Challenges:

- inconsistent triage across reviewers
- delayed escalation for serious incidents
- manual evidence checks are repetitive
- hard to reconstruct decisions during audit

## Slide 3: What This System Does

The system helps with first-line compliance evaluation.

It:

- evaluates incident submissions against control rules
- assigns risk and recommends next action
- routes investigation-required cases to human reviewers
- records every lifecycle step

## Slide 4: Controls Implemented

Current control set:

- CONDUCT-HARASSMENT-001
- CONDUCT-DISCRIMINATION-001
- CONDUCT-CLIENT-001
- CONDUCT-INTL-GOV-001

## Slide 5: End-to-End Workflow

1. Incident submitted.
2. Rule loaded by control_id.
3. Deterministic evaluation runs.
4. Risk and escalation metadata added.
5. Case either closes or enters review queue.
6. Manager assigns reviewer.
7. Reviewer investigates and submits final outcome.
8. Decision history is retained for audit.

## Slide 6: Decision States

- cleared: no additional action needed.
- policy_violation_confirmed: confirmed breach.
- insufficient_evidence: more evidence required.
- investigation_required: human investigation needed.

## Slide 7: Human Oversight and Governance

Human controls:

- manager-only assignment and reopen actions
- authenticated reviewer identity checks
- mandatory reviewer notes for final adjudication

Governance outputs:

- queue and SLA metrics
- reopen and override tracking
- append-only decision and review history

## Slide 8: Why It Matters

Business value:

- faster triage with consistent rules
- better focus on high-risk cases
- stronger audit defensibility
- measurable compliance operations

## Slide 9: Technical Snapshot

- API: FastAPI
- Storage: SQLite with current-state and history tables
- Auth: signed bearer tokens with role claims
- Rules: JSON control catalogs in data/rules
- Tests: API coverage for auth, lifecycle, metrics, and reporting

## Slide 10: One-Line Close

This system combines deterministic AI triage with human judgment to improve conduct compliance speed, consistency, and auditability.
