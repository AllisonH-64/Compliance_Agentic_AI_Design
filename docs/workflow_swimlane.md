# Workflow Swimlane: Employee Conduct Compliance MVP

## Swimlane Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Reporter as Employee or Reporter
    participant Agent as Compliance Agent
    participant Manager as Compliance Manager
    participant Analyst as Compliance Analyst
    participant Audit as Audit Store
    participant Reports as Metrics and Reporting

    Reporter->>Agent: Submit incident case (trigger)
    Note over Reporter,Agent: Inputs include case_id, incident_id, control_id, report and evidence context

    Agent->>Agent: Validate and normalize payload
    Agent->>Agent: Load control rule by control_id
    Agent->>Agent: Evaluate deterministic conduct logic
    Agent->>Audit: Save decision event (append-only history)

    alt Decision is cleared and review_required = false
        Agent-->>Reporter: Final output: case cleared
        Agent->>Reports: Update summary and queue metrics
    else Decision requires investigation
        Agent->>Reports: Add case to active review queue

        Manager->>Agent: Assign reviewer (oversight gate)
        Note over Manager,Agent: Requires role = compliance_manager
        Agent->>Audit: Save review_assigned and decision update

        Analyst->>Agent: Start review (oversight gate)
        Note over Analyst,Agent: Authenticated user must match reviewer_id
        Agent->>Audit: Save review_started and decision update

        Analyst->>Agent: Submit adjudication and notes (oversight gate)
        Agent->>Audit: Save review_submitted and review_completed
        Agent-->>Reporter: Final output: reviewed final decision
        Agent->>Reports: Update summary, queue, and SLA metrics

        opt New evidence or appeal
            Manager->>Agent: Reopen case with reason
            Agent->>Audit: Save case_reopened and new cycle state
        end
    end
```

## Decision Points Requiring Human Oversight

1. Assignment gate: only a compliance manager can assign a reviewer.
2. Start-review gate: only the authenticated assigned reviewer can start the case.
3. Final adjudication gate: reviewer determines final decision and outcome with notes.
4. Reopen gate: only authorized managers can reopen completed investigations.

## Dependencies

### Data Sources

- Incident intake payload and structured evidence fields
- Rule catalogs in data/rules
- Persisted decision and review records for queue and metrics

### Permissions

- Bearer token identity with role claims
- Allowed roles: employee, compliance_analyst, compliance_manager, auditor
- Manager-only assignment and reopen actions

### System Access

- API endpoints for evaluate, review lifecycle, queue, metrics, and summary
- SQLite availability for current state and append-only history
- Rule catalog read access for control resolution
