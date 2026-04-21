# Agentic System Design for Detecting Compliance Problems

## 1. Purpose

Design an agentic AI system that continuously checks business processes, documents, transactions, and model outputs for compliance problems. The system should detect likely issues early, explain why something may be non-compliant, route ambiguous cases to a human reviewer, and maintain an auditable record of every decision.

This design is domain-agnostic and can be adapted to:

- regulatory compliance
- internal policy compliance
- AI governance and ISO 42001 controls
- data privacy and security controls
- procurement, finance, HR, and operational controls

## 2. Core Outcome

The system should answer five questions reliably:

1. What obligation or rule applies?
2. What evidence is available?
3. Does the evidence satisfy the rule?
4. How confident is the conclusion?
5. What action should happen next?

## 2A. Recommended Project Framing

For this repository, the clearest practical workflow is gifts, meals, entertainment, and travel compliance.

Why this workflow fits well:

- it is a real Ethics and Compliance process, not just a finance control
- it combines clear policy thresholds with ambiguous exceptions
- it naturally requires human review for higher-risk cases
- it is easy to model with a small MVP and expand later into anti-bribery risk factors

## 3. Design Principles

- Human accountable: AI flags and recommends; humans approve high-impact actions.
- Evidence first: every finding must cite source evidence.
- Policy traceability: every rule evaluation must map back to a regulation, standard, or internal policy.
- Risk-based routing: higher-risk cases receive more scrutiny and lower automation.
- Explainable outcomes: users should see why a case passed, failed, or needs review.
- Audit by default: store inputs, rule versions, prompts, outputs, and reviewer actions.
- Least privilege: agents access only the data they need.

## 4. High-Level Architecture

The system is organized as a multi-agent workflow around a central compliance case.

### Inputs

- policies and regulations
- internal procedures and control libraries
- contracts and vendor documents
- emails, tickets, forms, and workflow records
- transactions and operational logs
- AI system outputs and usage logs

### Outputs

- compliance findings
- severity and confidence scores
- remediation recommendations
- escalation decisions
- audit trail

### Main Platform Components

1. Ingestion layer
   Collects documents, events, and records from enterprise systems.

2. Knowledge layer
   Stores structured obligations, control mappings, reference documents, and prior decisions.

3. Agent orchestration layer
   Coordinates specialized agents and manages the workflow for each case.

4. Decision layer
   Produces pass, fail, or review-required decisions with justification.

5. Human review layer
   Supports compliance analysts and control owners in reviewing high-risk findings.

6. Audit and monitoring layer
   Tracks performance, drift, false positives, overrides, and system health.

## 5. Agent Roles

### A. Intake Agent

Purpose:
Create a compliance case from a trigger.

Responsibilities:

- identify event type
- assign business context
- attach available metadata
- determine the initial control domain

Example triggers:

- new contract uploaded
- payment exceeds threshold
- employee access request submitted
- AI-generated report prepared for external use

### B. Policy Interpreter Agent

Purpose:
Convert regulations and policies into operational checks.

Responsibilities:

- parse policies into obligations, exceptions, and thresholds
- map obligations to business processes and control owners
- maintain a versioned rule catalog

Output example:

- obligation: customer data must not be retained beyond the allowed period
- evidence required: retention schedule, deletion log, system metadata
- breach condition: retained longer than approved period without exemption

### C. Evidence Collection Agent

Purpose:
Gather the evidence needed to test the relevant obligations.

Responsibilities:

- query source systems
- retrieve supporting documents
- normalize evidence into a standard case format
- identify missing or conflicting evidence

### D. Compliance Reasoning Agent

Purpose:
Evaluate whether evidence satisfies the rule.

Responsibilities:

- compare evidence against obligations
- detect exceptions or missing approvals
- reason across multiple sources
- produce a structured finding with rationale

Output example:

- status: likely non-compliant
- reason: approval missing and threshold exceeded
- evidence: invoice, approval record search result, policy clause
- confidence: 0.84

### E. Risk Scoring Agent

Purpose:
Determine how serious and urgent the issue is.

Responsibilities:

- estimate impact and likelihood
- account for regulatory exposure, customer harm, and recurrence
- prioritize review queues

Illustrative risk dimensions:

- legal exposure
- financial impact
- privacy impact
- reputational risk
- operational criticality
- customer harm potential

### F. Remediation Agent

Purpose:
Recommend the next best action.

Responsibilities:

- propose remediation steps
- identify required approvers
- draft analyst-ready case notes
- trigger workflow tasks where permitted

Example actions:

- request missing approval
- freeze transaction pending review
- notify data protection officer
- open corrective action plan

### G. Human Review Agent

Purpose:
Prepare cases for human adjudication.

Responsibilities:

- summarize the case in analyst language
- highlight the exact rule and evidence gap
- show confidence and uncertainty
- capture reviewer decision and feedback

### H. Learning and Governance Agent

Purpose:
Improve the system without changing controls silently.

Responsibilities:

- analyze false positives and false negatives
- propose rule updates for approval
- monitor drift in document structure or process behavior
- track model quality by control type

## 6. End-to-End Workflow

1. A trigger creates a compliance case.
2. The Intake Agent classifies the case and assigns relevant domains.
3. The Policy Interpreter Agent retrieves the applicable obligations.
4. The Evidence Collection Agent gathers structured and unstructured evidence.
5. The Compliance Reasoning Agent evaluates evidence against the rule set.
6. The Risk Scoring Agent sets severity, urgency, and review priority.
7. The system either:
   - auto-closes low-risk compliant cases
   - auto-routes low-confidence or high-risk cases to human review
   - auto-executes limited remediation where explicitly allowed
8. A human reviewer approves, rejects, or revises the finding.
9. The final decision and supporting evidence are stored in the audit trail.
10. Reviewer feedback is used to improve prompts, retrieval, and rules under change control.

## 7. Decision Logic

Each compliance check should produce a structured result.

### Decision States

- compliant
- non-compliant
- insufficient evidence
- exception applies
- human review required

### Minimum Decision Record

- case ID
- control ID
- policy version
- source systems consulted
- evidence references
- reasoning summary
- severity score
- confidence score
- recommended action
- human reviewer outcome if applicable
- timestamp and model version

## 8. Knowledge Model

The design works best if policies are converted into a machine-usable control model.

### Core Entities

- obligation
- control
- evidence artifact
- exception
- threshold
- business process
- system owner
- reviewer decision
- remediation action

### Example Mapping

- regulation clause -> obligation
- internal standard -> control
- workflow record -> evidence artifact
- approved waiver -> exception

This model should live in a versioned repository or governance database so that every finding can be reproduced later.

## 9. Retrieval and Reasoning Strategy

The system should not rely on a single LLM prompt. It should use layered reasoning.

### Recommended Strategy

- deterministic rules for clear thresholds and mandatory approvals
- retrieval-augmented generation for policy interpretation and evidence summarization
- LLM reasoning for ambiguous, multi-document, context-heavy cases
- confidence gating to force human review when evidence is incomplete or reasoning is weak

### Why this matters

- pure rules are too brittle for messy documents
- pure LLM reasoning is too variable for regulated decisions
- the combined approach gives stronger control and better auditability

## 10. Human-in-the-Loop Controls

The system should never fully automate material decisions without explicit approval from the organization.

### Mandatory Human Review Scenarios

- high-severity findings
- customer-impacting actions
- disciplinary or employment-related cases
- regulatory reporting decisions
- uncertain evidence or conflicting sources
- first-time rule deployments

### Reviewer Interface Should Show

- the exact rule that was evaluated
- evidence excerpts and source links
- the agent's reasoning summary
- alternative interpretations if uncertainty is high
- recommended next action

## 11. Guardrails and Safety Controls

### Technical Controls

- role-based access control
- prompt and tool restrictions by agent role
- source allow-listing for evidence retrieval
- PII redaction in logs where possible
- output schema validation
- model fallback and timeout handling

### Governance Controls

- approved model inventory
- prompt version control
- testing before rule release
- periodic control validation
- override logging for all human changes
- retention schedule for case records

## 12. Metrics

Measure system performance at three levels.

### Detection Quality

- precision
- recall
- false positive rate
- false negative rate
- reviewer agreement rate

### Operational Performance

- mean time to detect
- mean time to review
- queue backlog by severity
- evidence retrieval success rate

### Governance Performance

- percentage of findings with complete evidence
- percentage of cases with traceable policy mapping
- override frequency
- drift incidents detected

## 13. Example Use Cases

### Use Case 1: Procurement Compliance

Problem:
A purchase order above a threshold may require two approvals and vendor due diligence.

System behavior:

- detect new purchase order
- retrieve threshold rule and vendor policy
- inspect approvals and vendor screening status
- flag missing second approval or missing due diligence
- route high-value breaches to procurement compliance reviewer

### Use Case 2: Data Privacy Compliance

Problem:
Sensitive data may be retained too long or shared without basis.

System behavior:

- inspect retention metadata and sharing records
- compare against retention rules and lawful basis requirements
- detect expired retention or unsupported sharing
- recommend deletion, review, or incident escalation

### Use Case 3: AI Governance Compliance

Problem:
An AI-generated output may violate disclosure, review, or risk assessment requirements.

System behavior:

- detect AI-generated artifact
- verify disclosure label, approval workflow, and model risk status
- flag missing review or missing documentation
- escalate if output is customer-facing or high-impact

## 14. MVP Design

Start with a narrow scope instead of an enterprise-wide rollout.

### MVP Scope

- one compliance domain
- one or two source systems
- 10 to 20 high-value rules
- analyst review queue
- audit log and dashboard

### MVP Agent Set

- Intake Agent
- Policy Interpreter Agent
- Evidence Collection Agent
- Compliance Reasoning Agent
- Human Review Agent

### MVP Success Criteria

- findings are evidence-backed
- reviewers can reproduce decisions
- false positives are manageable
- the system reduces manual review time

## 15. Target Technology Pattern

The design can be implemented using this pattern:

- event bus or workflow trigger for intake
- document store plus vector index for policies and prior cases
- relational store for controls, case records, and audit history
- orchestration engine for agent workflow
- LLM with retrieval and structured output enforcement
- dashboard for analysts and compliance managers

## 16. Example Case Schema

```json
{
  "case_id": "CMP-2026-00421",
  "domain": "procurement",
  "trigger": "purchase_order_created",
  "control_id": "PROC-APP-002",
  "policy_version": "v3.4",
  "evidence": [
    {"type": "purchase_order", "ref": "PO-88314"},
    {"type": "approval_record", "ref": "APR-10219"}
  ],
  "finding": "non_compliant",
  "reason": "second approval missing for threshold breach",
  "severity": "high",
  "confidence": 0.91,
  "recommended_action": "route_to_procurement_compliance",
  "human_review_required": true
}
```

## 17. Operating Model

### Business Ownership

- compliance team owns policy interpretation
- control owners own remediation actions
- data owners approve source access
- AI governance or risk team owns model oversight

### Change Management

- new rules require approval
- changed prompts require testing
- model changes require regression checks
- retired controls remain historically reproducible

## 18. Key Risks and Mitigations

### Risk: False confidence

Mitigation:
Require evidence citation, confidence thresholds, and human review for sensitive cases.

### Risk: Policy ambiguity

Mitigation:
Store approved interpretations and force escalation when rules are unclear.

### Risk: Missing data

Mitigation:
Use an insufficient-evidence state instead of guessing.

### Risk: Silent drift

Mitigation:
Monitor changes in upstream processes, document formats, and reviewer override rates.

### Risk: Over-automation

Mitigation:
Restrict autonomous actions to low-risk, reversible actions.

## 19. Recommended Implementation Phases

1. Define the compliance domain, rule catalog, and severity model.
2. Build the evidence schema and policy knowledge base.
3. Implement the intake, retrieval, reasoning, and review workflow.
4. Pilot with human review on all findings.
5. Measure quality and refine rules, prompts, and routing.
6. Introduce selective automation only after control validation.

## 20. Summary

The right agentic compliance system is not a single chatbot. It is a controlled multi-agent workflow that converts policies into testable obligations, gathers evidence, reasons against those obligations, scores risk, escalates uncertainty, and preserves an audit trail.

If implemented this way, the system can improve detection speed and consistency without losing the human accountability that compliance functions require.

## 21. Reference Implementation Architecture

To make this a functioning agent, the system should be implemented as a small set of services with clear interfaces rather than one large application.

### Recommended Build Pattern

- API gateway for external clients and UI
- orchestration service for case workflows and agent coordination
- policy service for rule storage, versioning, and retrieval
- evidence service for document and system connectors
- decision service for compliance evaluation and risk scoring
- review service for analyst actions and overrides
- audit service for immutable decision logging

### Suggested Technology Stack

This is a pragmatic stack for a first working version:

- backend language: Python 3.12
- API framework: FastAPI
- schema validation: Pydantic
- agent orchestration: LangGraph or a lightweight state-machine workflow
- asynchronous jobs: Celery with Redis, or Temporal if long-running workflows are expected
- relational database: PostgreSQL
- vector retrieval: pgvector in PostgreSQL for the MVP
- document storage: Azure Blob Storage, AWS S3, or local object storage such as MinIO
- OCR and document extraction: Azure Document Intelligence or AWS Textract
- authentication: Microsoft Entra ID or another OIDC provider
- frontend: React with a simple analyst review console
- observability: OpenTelemetry plus Prometheus and Grafana

If the target environment is Microsoft-heavy, an Azure-first build is the most operationally coherent:

- FastAPI services deployed to Azure Container Apps or AKS
- Azure Service Bus for eventing
- Azure Blob Storage for evidence artifacts
- Azure Database for PostgreSQL
- Azure AI Search or PostgreSQL plus pgvector for retrieval
- Azure Document Intelligence for extraction
- Microsoft Entra ID for access control

## 22. Service Architecture

### A. API Gateway

Purpose:
Provide a single entry point for the web UI, source systems, and automation clients.

Responsibilities:

- authenticate callers
- authorize by role and domain
- route requests to internal services
- apply rate limiting and request logging

### B. Case Orchestrator Service

Purpose:
Act as the runtime brain of the system.

Responsibilities:

- create and manage case state
- invoke agents in sequence or conditionally
- enforce retries, timeouts, and escalation logic
- emit events for review, remediation, and audit

Recommended internal states:

- created
- classified
- policy_mapped
- evidence_collected
- evaluated
- risk_scored
- awaiting_human_review
- closed

### C. Policy Service

Purpose:
Store and serve machine-usable compliance rules.

Responsibilities:

- manage control catalog
- version obligations and exceptions
- map business domains to controls
- support retrieval of policy clauses and approved interpretations

### D. Evidence Service

Purpose:
Connect to source systems and normalize evidence.

Responsibilities:

- ingest files, forms, transactions, and audit logs
- call OCR and extraction pipelines
- standardize metadata and evidence references
- maintain evidence lineage back to the source system

### E. Decision Service

Purpose:
Run deterministic checks and LLM-assisted reasoning.

Responsibilities:

- execute threshold rules
- run policy-aware reasoning on ambiguous cases
- assign confidence and severity
- return a structured decision record

### F. Review Service

Purpose:
Support analyst adjudication.

Responsibilities:

- expose review queues
- store reviewer decisions and rationale
- support override workflows
- send feedback back into governance metrics

### G. Audit Service

Purpose:
Preserve reproducibility and defensibility.

Responsibilities:

- log each agent invocation
- store prompts, model IDs, policy versions, and evidence references
- record human decisions and overrides
- provide exportable audit reports

## 23. Agent Runtime Design

The agent should run as a controlled workflow, not as free-form autonomous looping.

### Recommended Runtime Pattern

1. Receive a case trigger.
2. Load the applicable workflow template by domain.
3. Run deterministic checks first.
4. Run evidence retrieval and normalization.
5. Invoke LLM reasoning only where deterministic logic is insufficient.
6. Validate output against a strict JSON schema.
7. Apply confidence and risk thresholds.
8. Either close, escalate, or queue for review.
9. Log everything needed for replay.

### Why this runtime pattern is preferred

- deterministic checks are cheaper and more stable
- LLM reasoning is reserved for ambiguity and document-heavy cases
- schema validation prevents unusable outputs
- stateful orchestration gives replayability and control

## 24. Concrete Data Stores

Each storage layer should have a narrow purpose.

### PostgreSQL

Use for:

- case records
- control catalog
- structured evidence metadata
- reviewer decisions
- remediation tasks
- audit event metadata

Illustrative tables:

- cases
- controls
- obligations
- policy_versions
- evidence_items
- findings
- reviews
- remediation_actions
- agent_runs

### Object Storage

Use for:

- uploaded policies
- contracts and forms
- OCR outputs
- evidence snapshots
- exported reports

### Vector Index

Use for:

- policy clause retrieval
- prior-case similarity search
- approved interpretation lookup

For the MVP, pgvector is sufficient. A dedicated retrieval engine can be added later if scale or ranking quality becomes a constraint.

### Optional Graph Store

Use only if cross-entity relationship analysis becomes important, for example:

- third-party networks
- cross-system approval chains
- repeated actor-pattern anomalies

This is not required for the first working version.

## 25. API Design

The platform should expose clear service APIs and keep the LLM behind internal boundaries.

### External APIs

#### POST /api/cases/intake

Creates a compliance case from a source trigger.

Example request:

```json
{
  "domain": "procurement",
  "trigger_type": "purchase_order_created",
  "source_system": "erp",
  "source_ref": "PO-88314",
  "submitted_by": "workflow@erp.local"
}
```

#### POST /api/cases/{case_id}/evaluate

Starts or restarts evaluation.

#### GET /api/cases/{case_id}

Returns the full case state, findings, and evidence references.

#### GET /api/cases/{case_id}/audit

Returns the execution trail for that case.

#### POST /api/reviews/{review_id}/decision

Stores analyst action.

Example request:

```json
{
  "reviewer": "analyst@company.com",
  "decision": "confirmed_non_compliant",
  "comment": "Threshold exceeded and no second approval exists"
}
```

#### POST /api/policies/sync

Triggers policy ingestion and rule extraction from approved documents.

### Internal Service APIs

The orchestrator should call internal services with typed contracts.

#### Policy resolution contract

Input:

- domain
- event type
- business unit
- jurisdiction

Output:

- applicable controls
- obligations
- thresholds
- exceptions
- policy version references

#### Evidence retrieval contract

Input:

- case ID
- required evidence types
- source references

Output:

- normalized evidence bundle
- missing evidence list
- source lineage

#### Decision contract

Input:

- case metadata
- policy bundle
- evidence bundle

Output:

- finding state
- rationale
- evidence citations
- confidence score
- severity score
- recommended action

## 26. Minimum Functional Agent Design

For the first functioning agent, keep the scope narrow.

### Recommended First Domain

Procurement approval compliance is a good starting point because:

- the rules are often threshold-based
- source systems are structured
- analyst validation is straightforward
- the false-positive cost is manageable

### Minimum Functional Features

- ingest purchase order events
- retrieve approval policy and threshold rules
- query approval records and vendor due diligence status
- determine pass, fail, or review-required
- show the result in an analyst queue
- persist an audit trail

### Minimum Agent Chain

1. Intake Agent
2. Policy Resolver
3. Evidence Collector
4. Rule Evaluator
5. LLM Reasoner for exceptions only
6. Risk Scorer
7. Review Router

This is enough to produce a functioning system without introducing unnecessary complexity.

## 27. Decision Engine Design

The decision engine should combine rule-based logic with constrained LLM reasoning.

### Rule Engine Responsibilities

- numeric threshold checks
- mandatory approval presence checks
- date and retention checks
- exception existence checks

### LLM Responsibilities

- summarize long policies into the active clause context
- interpret evidence from semi-structured documents
- explain why a finding is likely non-compliant
- identify ambiguity and explicitly declare uncertainty

### Required Output Schema

```json
{
  "finding": "non_compliant",
  "reasoning": "Purchase order exceeds the threshold for dual approval, but only one approval record was retrieved.",
  "evidence_citations": [
    "policy:PROC-APP-002:v3.4:clause_7",
    "erp:PO-88314",
    "workflow:APR-10219"
  ],
  "confidence": 0.91,
  "severity": "high",
  "requires_human_review": true,
  "recommended_action": "route_to_procurement_compliance"
}
```

Any LLM response that does not conform to schema should be rejected and retried once, then routed to manual review if still invalid.

## 28. Security and Access Model

The system will handle sensitive operational and compliance data, so security needs to be designed in from the start.

### Required Controls

- OIDC-based authentication
- role-based access control by function and compliance domain
- per-connector service identities
- encrypted evidence storage
- field-level masking for PII where possible
- immutable audit event logging
- prompt logging restricted to approved administrators

### Core Roles

- compliance_analyst
- control_owner
- reviewer_manager
- policy_admin
- platform_admin
- read_only_auditor

## 29. Observability and Reliability

### Reliability Controls

- idempotent case creation
- dead-letter queue for failed events
- retry policy for connector failures
- timeout policy for LLM and OCR calls
- fallback to insufficient-evidence state on partial failure

### Telemetry to Capture

- case throughput
- evaluation latency per stage
- retrieval latency by connector
- model response validity rate
- percentage of cases escalated to human review
- override rate by control

## 30. Deployment Topology

### MVP Topology

- one FastAPI backend
- one background worker process
- PostgreSQL with pgvector
- object storage bucket or container
- one analyst web UI
- one LLM provider integration

This is sufficient for a pilot.

### Scaled Topology

- separate services for orchestrator, policy, evidence, review, and audit
- event bus between services
- multiple workers for document extraction and evaluation
- dedicated retrieval service
- SIEM integration for audit and alert forwarding

## 31. Build Sequence

The fastest path to a functioning system is:

1. Define the first domain and 10 to 20 exact rules.
2. Create the PostgreSQL schema for cases, controls, evidence, findings, and reviews.
3. Build the FastAPI endpoints for case intake, evaluation, retrieval, and review.
4. Implement the orchestrator with deterministic rules only.
5. Add document retrieval and evidence normalization.
6. Add constrained LLM reasoning for exception handling and explanation.
7. Build the analyst queue UI.
8. Add audit exports and metrics.

## 32. Recommendation

If the objective is a working agent quickly, do not start with every compliance domain. Build one domain end to end with:

- FastAPI
- PostgreSQL plus pgvector
- object storage
- a simple workflow orchestrator
- a small React review console
- one LLM-backed reasoning step behind schema validation

That produces a real, operable compliance agent that can be tested with analysts, measured, and safely expanded.
