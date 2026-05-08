# Compliance Agentic AI — Explained Simply

## What Is It?

A company has rules about spending money on things like client dinners, gifts, and entertainment. Someone has to check that employees are following those rules. Doing that by hand — reading every receipt and form — takes a long time and people make mistakes.

This AI agent is an **automated rule-checker**. It reads the expense submissions, applies the company's policy, and decides what to do — instantly and consistently, every time.

---

## The Restaurant Scenario

> **Alex** works in sales. He takes a potential client out to dinner at a restaurant and spends **$200**. He submits an expense report the next day.

Here is exactly what happens, step by step:

---

### Step 1 — Alex Submits the Expense

Alex fills out a form with:
- Amount: $200
- Purpose: Client dinner
- Receipt: attached (photo of the bill)
- Pre-approval: none — he didn't ask before going

The form hits the system and the AI agent wakes up.

---

### Step 2 — The AI Reads the Submission

The agent pulls in Alex's case and loads the relevant company policy:

> **Policy ETH-GIFT-001:** Any spend of **$150 or more** on gifts, meals, or entertainment requires a **pre-approval from a compliance manager** before the money is spent.

> **Policy ETH-GIFT-002:** Any spend of **$150 or more** also requires a **receipt** as evidence.

---

### Step 3 — The AI Runs Its Checks

| # | Check | What the AI Looks For | Alex's Case | Result |
|---|---|---|---|---|
| 1 | **Threshold** | Is $200 ≥ $150? | Yes | Approval and receipt are both required |
| 2 | **Pre-approval** | Is there a compliance manager approval on file? | No approval found | ❌ FAIL |
| 3 | **Receipt** | Is a receipt attached? | Yes, receipt present | ✅ PASS |
| 4 | **Risk signals** | High-risk client? Pattern of splitting bills? Unusual geography? | No flags raised | ✅ LOW RISK |

---

### Step 4 — The AI Makes a Decision

Because Check #2 failed, the agent cannot approve the case automatically. It stamps the case:

```
Decision: NON-COMPLIANT
Reason:   Spend of $200.00 meets or exceeds the $150.00 threshold.
          Required pre-approval record is missing.
Action:   Routed to human review queue.
Logged:   2026-05-08T09:14:32Z  |  Agent v1.0
```

The agent does **not** close the case or punish Alex. It simply flags it and sends it to the review queue for a real person to look at.

---

### Step 5 — A Human Reviewer Takes Over

A compliance officer — let's call her **Maya** — gets assigned Alex's case. She can see:
- The AI's findings
- The receipt Alex uploaded
- Alex's explanation (he forgot about the pre-approval rule)

Maya decides this looks like an honest mistake. She approves it as a one-time exception and writes a note explaining why.

```
Final Decision: APPROVED (Exception Granted)
Reviewer:       Maya Chen, Compliance Officer
Notes:          First offense, receipt present, business purpose confirmed.
                Employee reminded of pre-approval requirement.
Logged:         2026-05-08T11:02:45Z
```

---

### Step 6 — Everything Is Saved

Both the AI's decision and Maya's override are permanently stored. If the company ever gets audited, there is a full trail:

- Who submitted it
- What the AI found
- What the human decided
- Why

---

## What If Alex Had Done Everything Right?

If Alex had gotten pre-approval **before** the dinner, the AI's Check #2 would have passed. The case would have been automatically closed as **Compliant** — no human needed, done in seconds.

That is the point: the AI handles the clean cases instantly, and humans only spend time on the ones that genuinely need judgment.

---

## The Four Possible Outcomes

| Outcome | What It Means |
|---|---|
| ✅ **Compliant** | All checks passed — case closed automatically |
| ❌ **Non-Compliant** | A rule was broken — sent to human review |
| ❓ **Insufficient Evidence** | Info is missing — held until more is provided |
| ⚠️ **Human Review Required** | Checks passed but something looks risky — human must decide |

---

## One-Line Summary

> The AI reads Alex's dinner receipt, checks it against company rules in seconds, flags the missing pre-approval, and hands the case to a human reviewer — so the compliance team only deals with what actually needs their judgment.
