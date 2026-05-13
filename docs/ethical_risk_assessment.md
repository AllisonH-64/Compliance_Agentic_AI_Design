# Ethical and Risk Assessment: Compliance Agentic AI MVP

## Scope and System Context

This assessment covers the current employee-conduct compliance MVP implemented in this repository.

- Main function: evaluate incident submissions and route medium to critical risk cases for investigation.
- Core controls:
  - CONDUCT-HARASSMENT-001
  - CONDUCT-DISCRIMINATION-001
  - CONDUCT-CLIENT-001
  - CONDUCT-INTL-GOV-001
- Decision states: policy_violation_confirmed, cleared, insufficient_evidence, investigation_required.
- Review lifecycle: pending, assigned, in_review, reopened, completed.

## Risk Register

| Risk Area | Risk Description | Potential Harm | Likelihood | Impact | Key Controls | Residual Risk |
| --- | --- | --- | --- | --- | --- | --- |
| Bias and fairness | Rules or escalation logic may disproportionately impact specific teams, geographies, or role groups if policy assumptions are unevenly applied. | Unequal treatment, inconsistent scrutiny, trust loss. | Medium | High | Deterministic policy checks, explicit rule metadata, human override path, periodic override-pattern review. | Medium |
| Privacy and confidentiality | Case payloads may contain personal or sensitive business data (expense details, identifiers, notes). | Unauthorized exposure, regulatory breach, reputational damage. | Medium | High | Least-privilege access model, role-based endpoint protection, minimized required fields, auditability of access actions. | Medium |
| Over automation | Automatic closure of low-risk cases could hide contextual red flags not represented in payload fields. | Missed misconduct signals, delayed remediation. | Medium | High | Human-review-required state, exception routing, reviewer adjudication and override controls, queue metrics monitoring. | Medium |
| Incorrect or incomplete evidence | Missing incident reports or supporting evidence can be misinterpreted when context exists elsewhere. | False positives, process friction, unfair decisions. | High | Medium | Distinct insufficient_evidence state, structured evidence fields, analyst review before final adverse closure. | Medium |
| Policy drift and stale controls | Rule catalogs may become outdated relative to policy changes. | Systemic misclassification, audit and compliance gaps. | Medium | High | Versioned rule metadata, controlled update process, validation tests tied to control behavior. | Medium |
| Security and unauthorized actions | Improper assignment or review submissions by unauthorized users. | Decision tampering, integrity loss, governance failure. | Low to Medium | High | Role checks by endpoint, manager-only assignment, reviewer identity matching on start and submit. | Low |
| Audit integrity and explainability | Inability to reconstruct why a case was decided or overridden. | Weak defensibility in internal/external audits. | Low | High | Append-only decision and review history, event metadata (actor, role, event type, timestamp), rationale in decision records. | Low |
| Gaming and procedural workarounds | Submitters may omit context fields or minimize narrative detail to downplay severity. | Hidden misconduct risk and delayed escalation. | Medium | Medium to High | Required core fields, severity scoring logic, management review of reopen and override trends. | Medium |

## Human-in-the-Loop Controls

Human oversight is required at clearly defined decision points.

- Escalation to human review: decisions requiring investigation are routed to analysts to prevent fully automated handling of high-impact outcomes.
- Assignment gate: only compliance managers can assign review owners to ensure accountable case ownership.
- Start gate: only the authenticated assigned reviewer can start review to prevent unauthorized handling.
- Final adjudication gate: reviewers must provide final decisions plus notes to preserve accountable and explainable judgment.
- Override capture and reviewability: override outcomes are persisted and reportable so governance can detect where automation required correction.

## How This Maps to Agentic AI Course Principles

The current design aligns with core Agentic AI principles typically emphasized in the course.

- Human accountability over autonomous action: manager assignment controls, reviewer identity checks, and mandatory adjudication keep humans responsible for high-impact outcomes.
- Evidence-first reasoning: each decision includes evidence references and rationale, and missing evidence is surfaced explicitly as insufficient_evidence.
- Transparency and explainability: decision and review records capture control metadata, reasoning, confidence, severity, actor identity, and outcome notes.
- Risk-based routing and proportional autonomy: lower-risk incidents can be cleared while medium to critical risk or low-confidence cases are escalated.
- Auditability and governance by default: append-only lifecycle history and summary reporting support defensible monitoring and oversight.
- Least privilege and controlled access: role-based endpoint checks limit who can view, assign, and adjudicate cases.

## Priority Mitigations for Next Iteration

- Privacy hardening: add field-level minimization and retention rules, plus masking or tokenization for sensitive identifiers in logs where feasible.
- Fairness and bias monitoring: add periodic analytics across role, geography, and business unit to detect disproportionate escalation or override rates.
- Stronger identity assurance: replace header-based role assertion with stronger authentication and signed identity context.
- Anti-gaming signals: add detection for repeated respondent patterns, repeated allegation clusters, and suspicious submission timing.
- Governance cadence: define a recurring control review cycle for rule updates, false-positive analysis, and override trend review.

## How Each Safeguard Reduces Risk

- Deterministic policy checks: reduce bias and inconsistency by applying the same rule logic to comparable cases every time.
- Explicit insufficient_evidence state: reduces false accusations and over-automation by treating missing data as uncertainty instead of immediate policy_violation_confirmed.
- Investigation-required routing: reduces harmful automated outcomes by escalating ambiguous or high-risk cases to analysts.
- Manager-only reviewer assignment: reduces governance and misuse risk by ensuring accountable ownership of sensitive adjudication work.
- Reviewer identity matching: reduces tampering and unauthorized action risk by requiring the authenticated user to match the assigned reviewer for start and submit steps.
- Mandatory reviewer notes: reduces explainability and audit-defense risk by documenting why final decisions were made.
- Append-only history: reduces integrity and repudiation risk by preserving immutable lifecycle records for investigation and audit.
- Role-based access controls: reduce privacy and least-privilege risk by limiting who can view, assign, and adjudicate cases.
- Queue and SLA metrics: reduce operational blind-spot risk by highlighting stale or aging review cases before control failure.
- Override capture and reporting: reduce model-drift and hidden-error risk by exposing where human reviewers corrected automated outcomes.

## Assessment Conclusion

The MVP demonstrates a defensible ethical baseline for agentic compliance automation: deterministic checks, explicit uncertainty handling, mandatory human oversight for higher-risk outcomes, and auditable lifecycle records. The main residual risks are privacy exposure, fairness drift, and over-reliance on static thresholds, all of which are manageable through the next-iteration controls listed above.
