# Demo Script

A step-by-step walkthrough for presenting the Vendor Due-Diligence Gate live. Entirely local — no AWS account or credentials needed for this path (see `docs/aws_deployment.md` separately if you want to talk through the AWS deployment layer too).

## Setup (before you're in front of anyone)

```bash
pip install -r requirements.txt
python run_demo.py
```

One command, one terminal — starts the API in the background, seeds it with 12 cases across all 8 controls, and leaves the server running until you press Ctrl+C. (If you'd rather run the API and seeding as two separate steps, `python dev_server.py` in one terminal and `python demo_seed.py` in another does the same thing.)

Open `http://127.0.0.1:8000/docs` in a browser. That's your demo surface — every step below is a "Try it out" click in Swagger UI, or an equivalent `curl`/browser-console `fetch` call if you'd rather narrate from the terminal.

**Don't click or select text inside the terminal window `run_demo.py` is running in** — on some Windows terminal configurations (QuickEdit mode), doing so pauses or kills the process. Just leave it alone once it's up.

Auth for the demo: use the `X-User-Id` / `X-User-Role` header fields directly in Swagger UI (no token needed — `dev_server.py` runs with `COMPLIANCE_ALLOW_INSECURE_HEADERS=true`). Roles used below: `employee`, `compliance_analyst`, `compliance_manager`, `auditor`.

## 1. Open with the problem, not the tech

Say it in one breath: *"A compliance team can't manually review every vendor transaction — an approval gets skipped, a vendor's bank details change and nobody double-checks, a gift to a government official goes unnoticed. This is a deterministic gate that stands between a vendor transaction and the money moving."* (Full version: `docs/problem_statement.md`.)

## 2. Show the rule catalog

**`GET /rules`** (any role) — 8 controls come back. Point at one entry's `policy_references`:

> *"Every control cites what it's actually enforcing — this one's `PROC-GIFTS-HOSPITALITY-001` cites Barbados's Prevention of Corruption Act, 2021, not a made-up policy name. Where I couldn't confirm a real regulation, it says so explicitly instead of a placeholder — that's on `PROC-VENDOR-COI-001`."*

## 3. Evaluate a transaction — the deterministic core

**`POST /evaluate`** as `employee`. Three quick contrasts, in order:

**a) A compliant case** — body from `examples/vendor_transaction_compliant.json`. Result: `approved`, `low` risk, auto-closed. *"The easy case doesn't bother anyone."*

**b) A gift to a government official** — body from `examples/vendor_transaction_gift_government_official_missing_approval.json` (only $40!). Result: `insufficient_evidence`, `critical` risk. *"Amount doesn't matter here — any gift to a government official needs pre-approval, because that's where the criminal liability is."*

**c) A failed vendor payment verification** — body from `examples/vendor_transaction_payment_change_verification_failed.json`. Result: `blocked`, `critical` risk, signal `SIG-PAYMENT-CHANGE-VERIFICATION-FAILED`. *"This is the business-email-compromise fraud pattern — someone impersonates a vendor and asks for a bank-detail change. This is the gate that catches it before the money moves, not after."*

## 4. Show the review queue and a full lifecycle

**`GET /reviews/queue`** (as `auditor`) — the pending/assigned/in-review cases from setup are all there.

Walk `CASE-2011` (the conflict-of-interest case) through its full history, already seeded:

- **`GET /reviews/CASE-2011`** — completed, then reopened. *"A manager originally cleared this — a family relationship with the vendor, disclosed and judged arm's-length. Then it got pulled back open for a quarterly audit follow-up. Nothing about the original decision was erased — the case just moved into a new review cycle."*
- **`GET /decisions/CASE-2011`** — point at `review_cycle_id: 2` and `reopen_reason`.

If you want to drive a live example instead of just showing the seeded one: assign `CASE-2008` (**`POST /reviews/CASE-2008/assign`** as `compliance_manager`, `reviewer_id: "analyst-1"`), start it (**`POST /reviews/CASE-2008/start`** as `compliance_analyst`), then submit it (**`POST /reviews/CASE-2008`**, `final_decision: "approved"`).

## 5. Governance dashboard — the "so what"

**`GET /dashboard/summary`** (as `auditor`). This is the payoff screen:

- Per-control breakdown — 8 controls, real traffic on each.
- `top_triggered_signals` — which specific risk patterns are firing most.
- `pending_notifications_by_recipient` — Procurement/Legal/Finance workload, computed automatically per decision, not manually tracked.

*"This is what a compliance manager actually looks at Monday morning — not 12 individual case files, but where the risk is concentrated and who needs to act on it."*

## 6. If there's time: the optional agent

If `ANTHROPIC_API_KEY` is set, `POST /agent/triage` takes a plain-English transaction description and produces the same structured decision — worth mentioning that the model never computes risk itself, it only calls the same `/evaluate` everything else goes through. Skip this section entirely if the key isn't set; it's explicitly optional (see README).

## Closing line

*"Every piece of this — the rules, the risk scoring, the audit trail — is deterministic and explainable. The only place an LLM touches this system is optional, and even there, it's not allowed to make the actual compliance call."*

## If something goes wrong live

- **Server not responding**: check terminal 1 is still running `dev_server.py`.
- **Empty dashboard/queue**: `demo_seed.py` didn't run, or `data/audit.db` was deleted after seeding — rerun it.
- **401 on a request**: missing `X-User-Id`/`X-User-Role` headers in Swagger UI's "Try it out" panel — they're plain header fields, not a global "Authorize" lock.
- **Want a clean re-run**: Ctrl+C `run_demo.py`, then run it again — it deletes `data/audit.db` and reseeds automatically every time.
- **Port already in use**: set `DEV_SERVER_PORT` to something else, e.g. `DEV_SERVER_PORT=8080 python run_demo.py` (PowerShell: `$env:DEV_SERVER_PORT = "8080"` first), and use that port in the URL instead.
