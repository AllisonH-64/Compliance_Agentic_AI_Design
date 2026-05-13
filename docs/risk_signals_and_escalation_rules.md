# Risk Signals and Escalation Rules Design

## Purpose

This document defines the escalation model for the conduct-incident MVP. The goal is to keep control evaluation deterministic and explainable while improving triage quality through explicit risk signals and risk-band routing.

Current controls are CONDUCT-HARASSMENT-001, CONDUCT-DISCRIMINATION-001, CONDUCT-CLIENT-001, and CONDUCT-INTL-GOV-001.

## Scope

This design applies to employee-conduct incident submissions evaluated by the existing workflow:

1. intake and normalization
2. deterministic control evaluation
3. review queue assignment and adjudication
4. persistent decision and review audit trail

The same pattern can later be adapted to adjacent compliance domains.

## Design Objectives

- Improve identification of genuinely high-risk cases that thresholds alone miss.
- Reduce analyst load by auto-closing low-risk cases when deterministic checks pass.
- Keep all escalations explainable with explicit signal-level rationale.
- Preserve human accountability for high-impact and ambiguous decisions.
- Support measurable queue health and service-level monitoring.

## Case Schema Extensions

The current case payload should be extended with risk-context fields.

### Proposed New Input Fields

- involved_party_role: respondent, complainant, witness, manager, client, vendor, unknown
- country_code: ISO country code where the incident occurred
- jurisdiction_risk_level: low, medium, high
- incident_category: harassment_bullying, discrimination, client_treatment, conflict_of_interest, international_governance, other
- prior_complaints_12m: count of prior complaints involving the respondent in the last 12 months
- involved_parties_count: number of directly involved individuals
- escalation_reference: prior case or escalation identifier when relevant
- protected_characteristic_mentioned: true when protected categories are explicitly involved

### Validation Rules

- Unknown or missing high-value context fields should not default to low risk.
- country_code should be required for international_governance incidents.
- prior_complaints_12m and involved_parties_count should be non-negative and bounded by schema validation.

## Risk Signal Catalog

Signals are deterministic, versioned, and independently testable. Each signal has a weight and rationale template.

### Signal Set V1

1. Missing incident report
- Trigger: incident_report absent where required
- Impact: insufficient_evidence with required investigation routing
- Why: formal incident documentation is required for defensible review

2. Protected characteristic mention
- Trigger: protected_characteristic_mentioned is true
- Impact: risk uplift and heightened review urgency

3. Prior complaint concentration
- Trigger: prior_complaints_12m exceeds configured thresholds
- Impact: risk uplift and prioritization for investigator queue

4. Multi-party impact
- Trigger: involved_parties_count exceeds configured threshold
- Impact: severity uplift due to broader organizational impact

5. High-risk jurisdiction
- Trigger: jurisdiction_risk_level is high
- Impact: escalation to international compliance and legal review pathways

6. International governance category
- Trigger: incident_category equals international_governance
- Impact: mandatory review with jurisdiction-aware action guidance

## Escalation Logic

Escalation combines deterministic outcomes with contextual risk signals.

### Step 1: Run deterministic controls

Evaluate existing policy checks first. This determines baseline decision state:

- compliant
- non-compliant
- insufficient evidence
- human review required

### Step 2: Compute risk profile

Calculate a transparent risk score and escalation reason set from triggered signals.

- risk score bands: `low`, `medium`, `high`, `critical`
- each band must include a list of triggered signal IDs and a short rationale

### Step 3: Apply routing matrix

Use a deterministic routing matrix:

- baseline policy_violation_confirmed -> mandatory investigation workflow
- baseline insufficient_evidence -> queue for evidence follow-up and investigator action
- baseline investigation_required -> queue with priority based on risk band
- baseline cleared plus low risk -> close with monitoring metadata only
- baseline cleared plus medium to critical risk -> route to investigation when policy requires

### Step 4: Priority assignment

Queue priority should derive from risk band and aging:

- critical: immediate, same-day SLA
- high: priority queue with short SLA
- medium: standard queue
- low: no queue unless deterministic policy requires investigation

## Auto-Close vs Mandatory Human Review

### Auto-Close Eligibility

A case can auto-close only when all of the following are true:

- deterministic controls return cleared
- risk band is `low`
- no escalation-floor signals are triggered
- no unresolved missing-context fields remain

### Mandatory Human Review Conditions

Human review is mandatory when any of the following apply:

- deterministic result is policy_violation_confirmed
- deterministic result is insufficient_evidence after follow-up timeout
- deterministic result is investigation_required
- risk band is high or critical
- protected characteristic or international governance signals trigger mandatory handling

## Reopened-Case Lifecycle Semantics

Reopen behavior must avoid overwriting historical reviewer decisions.

### Lifecycle States

- pending
- assigned
- in_review
- completed
- reopened

### Reopen Rules

- Reopen creates a new review cycle identifier while preserving prior cycles.
- Prior final reviewer outcomes remain immutable in history tables.
- Current case record stores the latest active cycle pointers.
- Reopen reason must be captured (`new_evidence`, `policy_update`, `appeal`, `audit_followup`, `other`).
- Reopened cases inherit prior risk signals but trigger full re-evaluation.

## Audit and Explainability Requirements

### Required Decision Record Fields

In addition to existing fields, capture:

- risk_band
- risk_score
- triggered_signal_ids
- signal_rationale
- escalation_decision
- escalation_policy_version
- review_cycle_id
- reopen_reason if applicable

### Required History Events

- risk_signals_computed
- escalation_applied
- case_reopened
- review_assigned
- review_started
- review_completed

Every event should include actor identity (system or human), timestamp, and policy/rule version references.

## Reporting and Monitoring Requirements

### Operational Metrics

- active queue by risk band
- SLA breach counts by risk band
- median and p95 time to adjudication
- reopen rate and reopen reasons
- cleared versus investigation-routed case rate

### Governance Metrics

- override rate by signal and control
- false-positive indicators from reviewer outcomes
- escalation distribution across roles and geographies
- insufficient_evidence recurrence by control

### Fairness and Drift Checks

- compare escalation and override rates across business units and geographies
- monitor changes in signal trigger frequency over time
- flag abrupt shifts after rule catalog changes

## Security and Authorization Direction

The current header-based RBAC is sufficient for MVP but should be hardened.

### Target Direction

- signed identity tokens with role and group claims
- service-level authorization policy, not endpoint-only checks
- immutable actor identity on all history events
- separation between submitter, reviewer, and approver authorities

## Implementation Phasing

### Phase A: Data and schema readiness

- add new case fields and validation rules
- add risk signal catalog structure and versioning
- update sample payloads and tests

### Phase B: Evaluation and routing

- implement signal computation after deterministic checks
- implement routing matrix and queue priority logic
- expose risk metadata in `/evaluate` and `/decisions` responses

### Phase C: Lifecycle and reporting

- add reopened-cycle semantics and event history support
- expand `/reviews/metrics` and `/reports/summary` with risk dimensions
- add governance analytics outputs

### Phase D: Auth hardening

- introduce stronger authentication and identity binding
- migrate role checks from headers to verified identity claims

## Acceptance Criteria

1. A low-severity cleared case closes with explicit risk metadata.
2. A medium to critical risk case is routed for mandatory investigation.
3. Reopened cases preserve prior reviewer outcomes and create a new cycle.
4. Reports show queue and SLA metrics segmented by risk band.
5. Every escalation decision is reconstructable from audit history.

## Open Questions

- Should medium-risk cleared cases always queue, or remain policy-configurable?
- What is the maximum acceptable evidence-follow-up timeout before forced escalation?
- Which governance owner approves risk-signal weight changes?
- How should low-confidence edge cases be handled when severity signals conflict?
