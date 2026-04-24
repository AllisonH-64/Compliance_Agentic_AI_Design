# Risk Signals and Escalation Rules Design

## Purpose

This document defines the next design layer after the current deterministic MVP controls. The goal is to preserve explainable rule checks while adding contextual risk signals that improve triage quality and analyst focus.

Current deterministic controls (`ETH-GIFT-001` and `ETH-GIFT-002`) remain in place as hard policy gates. Risk signals are additive and do not silently override core policy obligations.

## Scope

This design applies to gifts, meals, entertainment, and travel submissions evaluated by the existing workflow:

1. intake and normalization
2. deterministic control evaluation
3. review queue assignment and adjudication
4. persistent decision and review audit trail

The same pattern can later be adapted to vendor invoice review as described in `docs/mvp.md`.

## Design Objectives

- Improve identification of genuinely high-risk cases that thresholds alone miss.
- Reduce analyst load by auto-closing low-risk cases when deterministic checks pass.
- Keep all escalations explainable with explicit signal-level rationale.
- Preserve human accountability for high-impact and ambiguous decisions.
- Support measurable queue health and service-level monitoring.

## Case Schema Extensions

The current case payload should be extended with risk-context fields.

### Proposed New Input Fields

- `recipient_type`: `employee`, `customer`, `vendor`, `government_official`, `state_owned_entity`, `unknown`
- `country_code`: ISO country code where the interaction occurred
- `market_risk_level`: `low`, `medium`, `high` (from compliance-owned geography table)
- `business_purpose`: normalized free text or category label
- `prior_interactions_12m`: integer count of interactions with the same recipient in the last 12 months
- `exception_reference`: optional waiver or approved exception ID
- `event_context`: `contract_negotiation`, `active_tender`, `post_award`, `relationship_management`, `other`
- `submitted_by_role`: submitting employee role for segregation-of-duties checks
- `beneficiary_identifier`: recipient or organization reference for pattern detection

### Validation Rules

- Unknown or missing high-value context fields should not default to low risk.
- `recipient_type`, `country_code`, and `event_context` should be required when spend exceeds a configurable floor.
- `exception_reference` must map to an active, unexpired exception record to be considered valid.

## Risk Signal Catalog

Signals are deterministic, versioned, and independently testable. Each signal has a weight and rationale template.

### Signal Set V1

1. Government-official involvement
- Trigger: `recipient_type == government_official`
- Impact: immediate escalation floor to high
- Why: anti-bribery exposure even at lower spend levels

2. State-owned entity involvement
- Trigger: `recipient_type == state_owned_entity`
- Impact: risk uplift and mandatory review for medium-or-higher spend

3. High-risk geography
- Trigger: `market_risk_level == high`
- Impact: risk uplift and stricter evidence requirement

4. Repeated interactions pattern
- Trigger: `prior_interactions_12m` above configured threshold
- Impact: risk uplift for possible relationship-influence concerns

5. Tender or negotiation timing
- Trigger: `event_context in {contract_negotiation, active_tender}`
- Impact: mandatory review due to conflict or undue influence risk

6. Missing business-purpose clarity
- Trigger: empty or weak `business_purpose` classification
- Impact: insufficient evidence or review-required depending on other signals

7. Exception reference misuse
- Trigger: invalid, expired, or mismatched `exception_reference`
- Impact: non-compliant or review-required based on deterministic control result

8. Submission pattern anomalies
- Trigger: repeated near-threshold submissions by same submitter or beneficiary in short windows
- Impact: anti-gaming escalation and analyst review

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

- baseline `non-compliant` -> always human review
- baseline `insufficient evidence` -> request evidence and queue if unresolved
- baseline `human review required` -> queue with priority based on risk band
- baseline `compliant` + risk `low` -> auto-close
- baseline `compliant` + risk `medium` -> optional review queue based on policy toggle
- baseline `compliant` + risk `high` or `critical` -> mandatory human review

### Step 4: Priority assignment

Queue priority should derive from risk band and aging:

- `critical`: immediate, same-day SLA
- `high`: priority queue with short SLA
- `medium`: standard queue
- `low`: no queue unless deterministic policy requires review

## Auto-Close vs Mandatory Human Review

### Auto-Close Eligibility

A case can auto-close only when all of the following are true:

- deterministic controls return `compliant`
- risk band is `low`
- no escalation-floor signals are triggered
- no unresolved missing-context fields remain

### Mandatory Human Review Conditions

Human review is mandatory when any of the following apply:

- deterministic result is `non-compliant`
- deterministic result is `insufficient evidence` after evidence request timeout
- risk band is `high` or `critical`
- escalation-floor signals trigger (government official, active tender context)
- exception reference is present but fails validation

## Reopened-Case Lifecycle Semantics

Reopen behavior must avoid overwriting historical reviewer decisions.

### Lifecycle States

- `queued`
- `assigned`
- `in_review`
- `closed`
- `reopened`

### Reopen Rules

- Reopen creates a new review cycle identifier while preserving prior cycles.
- Prior final reviewer outcomes remain immutable in history tables.
- Current case record stores the latest active cycle pointers.
- Reopen reason must be captured (`new_evidence`, `policy_update`, `appeal`, `audit_followup`, `other`).
- Reopened cases inherit prior risk signals but trigger full re-evaluation.

## Audit and Explainability Requirements

### Required Decision Record Fields

In addition to existing fields, capture:

- `risk_band`
- `risk_score`
- `triggered_signal_ids`
- `signal_rationale`
- `escalation_decision`
- `escalation_policy_version`
- `review_cycle_id`
- `reopen_reason` (if applicable)

### Required History Events

- `risk_signals_computed`
- `escalation_applied`
- `case_auto_closed`
- `case_reopened`
- `evidence_request_sent`
- `evidence_request_expired`

Every event should include actor identity (system or human), timestamp, and policy/rule version references.

## Reporting and Monitoring Requirements

### Operational Metrics

- active queue by risk band
- SLA breach counts by risk band
- median and p95 time to adjudication
- reopen rate and reopen reasons
- auto-close rate vs human-reviewed rate

### Governance Metrics

- override rate by signal and control
- false-positive indicators from reviewer outcomes
- escalation distribution across roles and geographies
- exception-reference usage and invalidation rate

### Fairness and Drift Checks

- compare escalation and override rates across business units and geographies
- monitor changes in signal trigger frequency over time
- flag abrupt shifts after rule catalog changes

## Security and Authorization Direction

The current header-based RBAC is sufficient for MVP but should be hardened.

### Target Direction

- signed identity tokens with role and group claims
- service-level authorization policy (not endpoint-only checks)
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

1. A compliant low-risk case auto-closes with explicit risk metadata.
2. A compliant but high-risk context case is routed for mandatory human review.
3. Reopened cases preserve prior reviewer outcomes and create a new cycle.
4. Reports show queue and SLA metrics segmented by risk band.
5. Every escalation decision is reconstructable from audit history.

## Open Questions

- Should medium-risk compliant cases always queue, or remain policy-configurable by market?
- What is the maximum acceptable evidence-request timeout before forced escalation?
- Which governance owner approves risk-signal weight changes?
- How should conflict cases be handled when deterministic controls pass but a critical signal fires?
