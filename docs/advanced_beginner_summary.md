# Compliance Agentic AI: Advanced Beginner Summary

## What This Project Does

This project is a compliance assistant for workplace conduct incidents.

It helps teams review incidents such as:

- harassment and bullying
- discrimination allegations
- client treatment concerns
- international governance issues

The system is designed to make triage faster and more consistent, while keeping people in charge of final decisions.

## How It Works in Plain Terms

1. Someone submits an incident case.
2. The system checks which control rule applies.
3. It evaluates the case using deterministic logic (same rule behavior every time).
4. It assigns a risk level and decision recommendation.
5. If the case needs investigation, it goes to a human review queue.
6. A manager assigns a reviewer, and the reviewer completes adjudication.
7. Every step is logged for audit and reporting.

## Key Decisions You Will See

- cleared: no further action needed based on current evidence.
- policy_violation_confirmed: the incident is confirmed as a policy breach.
- insufficient_evidence: required evidence is missing.
- investigation_required: human review is required before closure.

## Why This Is Useful

- It reduces repetitive manual triage.
- It improves consistency in applying policy logic.
- It gives investigators a structured starting point.
- It keeps an audit trail for governance and assurance.

## Human Oversight Is Built In

The AI does not make final high-impact decisions alone.

- only authorized roles can assign and complete reviews
- reviewers must provide notes and final outcomes
- cases can be reopened when new evidence appears

This keeps accountability with compliance professionals.

## Technical Snapshot

- API framework: FastAPI
- Storage: SQLite (current state plus append-only history)
- Auth: signed bearer tokens with role claims
- Rules: JSON control catalogs in data/rules
- Tests: API tests for auth, lifecycle, metrics, and reporting

## How to Explain It in One Sentence

This is a rule-driven AI assistant that triages conduct incidents, routes risky cases to human investigators, and records every decision for auditability.
