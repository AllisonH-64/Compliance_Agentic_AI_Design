# Governance Operating Model

## Purpose

This document defines how governance is run for the Compliance Agentic AI workflow so that policy controls remain accountable, traceable, measurable, and auditable over time.

## Scope

Applies to:

- deterministic controls (CONDUCT-HARASSMENT-001, CONDUCT-DISCRIMINATION-001, CONDUCT-CLIENT-001, CONDUCT-INTL-GOV-001)
- contextual risk-signal logic and escalation routing
- review lifecycle and reopened-case handling
- authentication and authorization trust settings
- reporting, monitoring, and control-change operations

## Governance Structure

### Governance Bodies

1. Compliance AI Control Board (CACB)
- owns rule and signal governance
- approves production control changes
- resolves policy interpretation conflicts

2. Risk and Ethics Review Group (RERG)
- reviews fairness, override trends, and escalation behavior
- approves mitigations for bias or disproportionate impact

3. Security and Identity Authority (SIA)
- owns auth trust controls, token validation policy, and key lifecycle
- approves issuer/audience and key rotation configurations

### Meeting Cadence

- weekly: operational triage and exceptions
- monthly: KPI and fairness review
- quarterly: control library and policy-traceability audit

## Roles and Responsibilities (RACI)

| Activity | Compliance Manager | Compliance Analyst | Security Lead | Data Steward | Internal Audit |
| --- | --- | --- | --- | --- | --- |
| Rule threshold changes | A | C | I | C | I |
| Risk signal weight changes | A | R | I | C | I |
| Escalation matrix updates | A | R | I | C | I |
| Auth trust config changes | I | I | A/R | I | C |
| Override pattern review | A | R | I | C | C |
| Fairness review and remediation | A | R | I | C | C |
| Quarterly evidence audit | I | C | C | C | A/R |

Legend: `A` accountable, `R` responsible, `C` consulted, `I` informed.

## Decision Rights

1. Rules and thresholds
- final approver: Compliance Manager
- required evidence: impact note, updated tests, rollback steps

2. Risk signals and escalation
- final approver: CACB
- required evidence: override analysis, fairness impact, monitoring update

3. Auth trust controls
- final approver: SIA
- required evidence: key/issuer/audience validation plan, rollback path

4. Exceptions and waivers
- final approver: Compliance Manager
- required evidence: exception reference, expiration, compensating controls

## Policy-to-Control Traceability Register

Maintain a register with one row per control and signal.

Required columns:

- control_or_signal_id
- policy_source
- policy_clause_reference
- business_owner
- technical_owner
- effective_date
- last_reviewed_at
- next_review_due
- test_case_references
- reporting_metrics

## Change Management Workflow

1. Propose
- submit change request with rationale and impacted controls/signals

2. Assess
- analyze expected effects on queue volume, override rate, and fairness metrics

3. Validate
- update automated tests
- execute regression suite
- record expected KPI movement

4. Approve
- obtain required governance approvals based on decision rights

5. Release
- deploy with version tag and traceability record

6. Monitor
- track post-release KPI behavior for one full review cycle

7. Roll back (if required)
- trigger rollback when breach thresholds are exceeded

## Data Governance Requirements

1. Data classification
- classify case, review, and evidence fields as public/internal/confidential/restricted

2. Retention
- define retention by record type (decision, review, evidence metadata, history event)

3. Privacy controls
- minimize sensitive fields
- redact sensitive identifiers in operational logs where feasible

4. Access controls
- enforce least privilege by role
- keep immutable actor identity in lifecycle history

## Operational Governance Metrics

### Mandatory KPI Set

- active review count by risk band
- SLA breach count by risk band
- median and p95 review completion time
- reopen rate and reopen reasons
- auto-close rate vs human-reviewed rate
- override rate by control and signal
- insufficient-evidence rate

### Threshold Examples

- SLA breach rate: > 10 percent for two consecutive weeks triggers corrective action
- override rate: > 20 percent on a control triggers rule-quality review
- reopen rate: > 8 percent triggers lifecycle and evidence-quality analysis

## Fairness and Ethics Monitoring

1. Distribution analysis
- compare escalation, override, and reopen rates across geography, business unit, and role categories

2. Drift analysis
- detect sudden shifts in signal trigger frequencies after policy/rule updates

3. Remediation process
- open corrective action plan with owner, due date, and measurable closure criteria

## Security and Identity Governance

Current implementation supports:

- bearer token authentication
- key-id based secret trust (`COMPLIANCE_AUTH_KEYS_JSON`)
- optional issuer/audience checks (`COMPLIANCE_AUTH_ISSUER`, `COMPLIANCE_AUTH_AUDIENCE`)

Target production direction:

- asymmetric signing with managed key lifecycle
- periodic key rotation with cutover runbook
- issuer onboarding/offboarding control process
- incident response procedure for key compromise

## Audit and Assurance

1. Monthly control assurance sampling
- sample completed cases and verify policy alignment and evidence traceability

2. Quarterly independent review
- internal audit validates control operation, exception governance, and auth trust posture

3. Evidence package for review
- change approvals
- test run artifacts
- KPI trend snapshots
- exception and override logs

## Governance Artifacts

Maintain these artifacts in version control:

- governance operating model (this file)
- traceability register
- KPI scorecard
- change request templates
- approval logs and meeting minutes

## First 30-Day Rollout Plan

1. Week 1
- confirm governance owners and decision rights
- initialize traceability register template

2. Week 2
- baseline current KPI values
- define thresholds and alert routing

3. Week 3
- run first fairness/drift review cycle
- test rollback and incident playbook

4. Week 4
- conduct first governance board review
- publish remediation backlog and ownership
