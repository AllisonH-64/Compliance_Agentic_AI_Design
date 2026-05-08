# Executive Summary: Compliance Agentic AI MVP

## Problem Summary

The Compliance team handles a high volume of gifts and hospitality cases that require consistent checks for approval thresholds, receipt evidence, and policy exceptions. Manual triage across forms, receipts, and approval records is repetitive, slow, and can produce inconsistent outcomes, especially when evidence is incomplete or cases are ambiguous.

## Proposed Agent

A Compliance Agentic AI assistant performs deterministic policy evaluation, explains outcomes, and routes higher-risk or unclear cases to human reviewers. The system is designed to assist, not replace, compliance officers by combining rule-based checks with controlled human oversight and auditable records.

## Workflow Summary

1. Trigger: employee submits a case.
2. Agent intake: validates and normalizes case data.
3. Rule selection: loads applicable control and policy metadata.
4. Evaluation: applies deterministic checks and produces a structured decision.
5. Decision routing:
   - auto-close low-risk compliant cases
   - route non-compliant, insufficient-evidence, or ambiguous cases to the review queue
6. Human review:
   - manager assigns reviewer
   - reviewer starts review
   - reviewer submits final decision and notes
7. Final output: decision and review outcome are persisted, then metrics and reporting are updated.

## Key Risks

1. Bias and fairness drift in how cases are escalated or interpreted.
2. Privacy exposure from sensitive case data.
3. Over-automation that misses contextual red flags.
4. False positives from incomplete evidence.
5. Stale policies causing misclassification.
6. Unauthorized review actions.
7. Weak audit defensibility if rationale is not preserved.
8. Process gaming, such as threshold splitting.

## Safeguards

1. Deterministic policy checks for consistency.
2. Explicit insufficient-evidence state to avoid premature adverse decisions.
3. Human-review-required routing for higher-risk or ambiguous outcomes.
4. Manager-only assignment control.
5. Reviewer identity matching on start and submission.
6. Mandatory reviewer notes for accountable final adjudication.
7. Append-only decision and review history for audit integrity.
8. Role-based access controls to enforce least privilege.
9. Queue and SLA metrics to detect stalled risk cases.
10. Override capture and reporting to identify where automation needs improvement.

## Worked Example: Client Dinner Expense

> **Alex** works in sales. He takes a potential client to dinner and spends **$200**. He submits an expense report the next day with a receipt attached but no pre-approval.

**Step 1 — Submission received.** The agent validates and normalizes Alex's case data.

**Step 2 — Policy loaded.** The agent loads two applicable controls:
- ETH-GIFT-001: spend ≥ $150 requires compliance manager pre-approval.
- ETH-GIFT-002: spend ≥ $150 requires a receipt.

**Step 3 — Checks run.**

| # | Check | Alex's Case | Result |
|---|---|---|---|
| 1 | Threshold: is $200 ≥ $150? | Yes — both controls apply | — |
| 2 | Pre-approval on file? | No approval record found | ❌ FAIL |
| 3 | Receipt attached? | Yes, receipt present | ✅ PASS |
| 4 | Risk signals (client type, geography, pattern)? | No flags raised | ✅ LOW RISK |

**Step 4 — Decision stamped.**

```
Decision: NON-COMPLIANT
Reason:   Spend of $200.00 meets or exceeds the $150.00 threshold.
          Required pre-approval record is missing.
Action:   Routed to human review queue.
Logged:   2026-05-08T09:14:32Z  |  Agent v1.0
```

**Step 5 — Human review.** Compliance officer Maya Chen is assigned the case. She reviews the AI findings, the receipt, and Alex's explanation (first offense, forgot the rule). She grants a one-time exception and records her rationale:

```
Final Decision: APPROVED (Exception Granted)
Reviewer:       Maya Chen, Compliance Officer
Notes:          First offense, receipt present, business purpose confirmed.
                Employee reminded of pre-approval requirement.
Logged:         2026-05-08T11:02:45Z
```

**Step 6 — Audit trail persisted.** Both the agent decision and Maya's override are stored in the append-only history, satisfying audit requirements.

> If Alex had obtained pre-approval before the dinner, Check 2 would have passed and the case would have been auto-closed as **Compliant** — no human review needed.

---

## Expected Benefits for the Compliance Team

1. Faster triage: routine compliant cases are handled quickly, reducing manual burden.
2. Better consistency: policy checks are applied uniformly across cases.
3. Higher-quality reviews: analysts focus on exceptions and genuinely risky cases.
4. Stronger governance: clear accountability at assignment, review, and adjudication steps.
5. Better audit readiness: traceable decisions, reviewer actions, and event history.
6. Operational visibility: queue and SLA metrics improve workload and escalation management.
7. Continuous improvement: override and outcome data provide feedback for policy and control tuning.
