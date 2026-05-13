# Compliance Agentic AI - Explained Simply

## What Is It?

A company has rules for how workplace conduct incidents must be handled. Someone has to check each report, see if there is enough evidence, and decide whether an investigation is needed.

Doing that by hand for every case takes time and can be inconsistent. This AI agent acts like a fast assistant that follows policy rules the same way every time.

## A Simple Scenario

Jordan reports a harassment incident at work. Jordan writes details about what happened, but forgets to attach the formal incident report document.

Here is what the system does.

### Step 1 - Case Is Submitted

The case includes:

- case_id and incident_id
- incident description
- involved people and context
- attached evidence if available

### Step 2 - AI Loads the Right Rule

The system selects the harassment control and checks what evidence is required.

### Step 3 - AI Runs Checks

It checks things like:

- Is required incident documentation attached?
- Are protected characteristics mentioned?
- Are there prior complaints tied to the same respondent?
- How severe does this case appear based on the policy logic?

### Step 4 - AI Creates a Decision

Because the required incident report is missing, the system marks the case as insufficient_evidence and routes it to investigation review.

The AI does not make a final punishment decision. It flags the issue and sends it to trained reviewers.

### Step 5 - Human Reviewer Decides

A compliance reviewer is assigned, investigates, records notes, and submits the final decision.

### Step 6 - Everything Is Logged

The system saves:

- what the AI decided first
- what the human decided finally
- who did each action and when

That gives a full audit trail.

## Possible Outcomes

| Outcome | What It Means |
|---|---|
| cleared | Case can be closed based on current evidence |
| policy_violation_confirmed | Policy breach is confirmed |
| insufficient_evidence | More evidence is needed |
| investigation_required | Human investigation must continue |

## One-Line Summary

The AI quickly triages conduct reports, but people stay in charge of final investigation decisions.
