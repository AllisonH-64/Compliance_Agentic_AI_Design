# Workflow Swimlane: Gifts and Hospitality Compliance MVP

## Swimlane Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Employee
    participant Agent as Compliance Agent
    participant Manager as Compliance Manager
    participant Analyst as Compliance Analyst
    participant Audit as Audit Store
    participant Reports as Metrics and Reporting

    Employee->>Agent: Submit case (trigger)
    Note over Employee,Agent: Inputs: case_id, transaction_id, control_id, amount, currency, requestor_role, optional evidence

    Agent->>Agent: Validate and normalize payload
    Agent->>Agent: Load rule catalog by control_id
    Agent->>Agent: Evaluate deterministic controls
    Agent->>Audit: Save decision event (append-only history)

    alt Decision is compliant and review_required = false
        Agent-->>Employee: Final output: compliant decision
        Agent->>Reports: Update summary and queue metrics
    else Decision is non_compliant, insufficient_evidence, or human_review_required
        Agent->>Reports: Add case to active review queue

        Manager->>Agent: Assign reviewer (oversight gate)
        Note over Manager,Agent: Requires role = compliance_manager
        Agent->>Audit: Save review_assigned and decision update

        Analyst->>Agent: Start review (oversight gate)
        Note over Analyst,Agent: Authenticated user must match reviewer_id
        Agent->>Audit: Save review_started and decision update

        Analyst->>Agent: Submit final adjudication and notes (oversight gate)
        Agent->>Audit: Save review_submitted and review_completed
        Agent-->>Employee: Final output: reviewed final decision
        Agent->>Reports: Update summary, queue, and SLA metrics
    end
```

## Decision Points Requiring Human Oversight

1. Assignment gate: only a compliance manager can assign a reviewer.
2. Start-review gate: only the authenticated assigned reviewer can start the case.
3. Final adjudication gate: reviewer determines final decision and outcome with notes.
4. Exception-handling gate: ambiguous evidence or policy-scope mismatches route to human review.

## Dependencies

### Data Sources

- Case intake payload from request or expense workflow
- Rule catalogs in data/rules
- Approval evidence and receipt evidence when present
- Persisted decision and review records for queue and metrics

### Permissions

- Identity context headers: X-User-Id and X-User-Role
- Allowed roles: employee, compliance_analyst, compliance_manager, auditor
- Manager-only assignment and reviewer identity matching for start and submit actions

### System Access

- API endpoints for evaluate, review lifecycle, queue, metrics, and summary
- SQLite availability for current state and append-only history
- Rule catalog read access for control resolution
