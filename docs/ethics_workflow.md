# Ethics Workflow Concept

## Project Concept

This project is best framed as an Agentic AI assistant for gifts, meals, entertainment, and travel compliance. That is a real workflow owned by Ethics and Compliance teams because it sits at the intersection of anti-bribery rules, conflicts of interest, expense governance, and manager accountability.

The system does not replace compliance officers. It reduces manual triage by collecting the right evidence, applying the policy consistently, and routing only the cases that need judgment.

## The Business Problem

Large organizations receive a steady stream of requests and reimbursement submissions for customer meals, event tickets, travel, and other hospitality. Compliance teams need to answer the same questions repeatedly:

- Is the spend above the policy threshold?
- Was the required pre-approval obtained?
- Is receipt evidence attached?
- Does the case involve facts that make it higher risk than usual?
- Can the case be closed, or does an analyst need to review it?

Today that often means checking forms, receipts, policy PDFs, and approval records across multiple systems. The work is repetitive, time-sensitive, and easy to execute inconsistently.

## Where Agentic AI Fits

The agentic pattern works here because the workflow combines deterministic checks with incomplete evidence and occasional exceptions.

### Deterministic checks

- spend exceeds threshold
- approval is missing
- receipt is missing
- approver role does not match policy

### Judgment-heavy checks

- a delegated approver may be valid under a local exception
- a missing field may be explained in supporting documents
- repeated hospitality to the same external party may increase risk
- government official involvement may require escalation even if the amount is small

## Proposed Multi-Agent Workflow

### 1. Intake Agent

- receives a new hospitality request or expense claim
- creates a case record
- identifies the applicable control domain

### 2. Policy Mapping Agent

- retrieves the relevant policy version
- selects the threshold, required approver, and evidence obligations
- identifies exception paths that require analyst judgment

### 3. Evidence Collection Agent

- gathers the request form, approval metadata, and receipt artifacts
- normalizes evidence into a single case schema
- marks missing or conflicting evidence

### 4. Compliance Evaluation Agent

- runs deterministic checks first
- produces a structured decision, rationale, and confidence score
- distinguishes between non-compliance and insufficient evidence

### 5. Risk Routing Agent

- raises severity for higher-risk patterns
- prioritizes cases for the analyst queue
- recommends whether the case can be auto-closed or must be escalated

### 6. Human Review Agent

- prepares a concise analyst summary
- shows the rule, evidence, and uncertainty
- captures the reviewer decision, override, and notes

## MVP Mapping In This Repository

The current MVP already implements the first practical slice of this workflow.

- `ETH-GIFT-001`: pre-approval is required when spend is at or above 150 USD
- `ETH-GIFT-002`: receipt evidence is required when spend is at or above 75 USD
- `/evaluate`: runs the deterministic evaluation and produces a decision record
- `/reviews/queue`: shows active cases awaiting analyst action
- `/reviews/{case_id}/assign`, `/start`, and `POST /reviews/{case_id}`: support reviewer assignment, work in progress, and final disposition
- SQLite persistence provides a lightweight local audit trail

## Why This Is Practical

- the workflow is familiar to business stakeholders and compliance officers
- the control logic is easy to validate with sample cases
- the human review path is necessary and realistic, not artificial
- the design can grow from simple thresholds to richer anti-bribery screening without changing the operating model

## Recommended Next Iteration

To make the concept more representative of a production Ethics and Compliance workflow, extend the case schema with:

- recipient type, including government official or state-owned entity
- country or market risk
- business purpose of the event or gift
- prior interactions with the same recipient
- exception or waiver references

That would allow the agentic system to keep deterministic controls for core policy gates while using retrieval and reasoning only for the ambiguous cases where analyst judgment is actually required.