# Changelog

Build history for the Vendor Due-Diligence Gate, newest first. This repo pivoted through a few earlier domains (procurement → gifts/hospitality → employee conduct) before settling here — that history is in `git log` but not repeated below, since none of it describes the current codebase.

## Rebuilt and wired in the LLM triage agent

`orchestrator.py`/`router.py`/`tools.py` were pure scaffolding — never mounted into `app/main.py`, and stale enough that they wouldn't have worked even if mounted:

- `tools.py` called `GET /investigations/queue` and `GET /rules/current` (single-rule) instead of the current `GET /reviews/queue` and `GET /rules`; `POST /reviews/{case_id}/assign` sent `{"investigator": ...}` instead of the `{"reviewer_id": ...}` the API actually expects.
- `orchestrator.py` compared a decision's risk band against `HIGH_SEVERITY_BANDS = {"HIGH", "CRITICAL"}` using `result.get("severity_band")` — but the API returns `risk_band`, and values are lowercase (`"high"`/`"critical"`), so the human-confirmation gate for high-risk reviewer assignment could never actually trigger.
- Both files still referenced the four retired employee-conduct controls instead of the eight current procurement controls.

Fixed all of the above, renamed the vocabulary to the vendor-transaction domain, and updated the model ID. Extracted `app/auth.py` out of `app/main.py` (a clean lift, not a behavior change) so `router.py` can reuse the same RBAC without a circular import. The agent mounts best-effort — `app/main.py` wraps the import in `try/except ImportError` — so the AWS Lambda deployment (which excludes this scaffolding entirely) is unaffected either way. Verified directly against a live server: `get_active_rules` now returns all 8 controls, `get_open_reviews` hits the real endpoint, `assign_reviewer` sends the correct payload key.

## AWS deployment layer + problem statement

Added a real, `cdk synth --strict`-verified CDK (Python) app under `infra/`: two stacks (`VendorGateDataStack` for DynamoDB/S3/Cognito, `VendorGateApiStack` for the Lambda/API Gateway/audit-export pipeline), a Lambdalith wrapping the existing FastAPI app via Mangum, a native Cognito JWT authorizer, and a DynamoDB-Streams-to-S3 audit export. `app/storage.py` became a thin backend dispatcher (`COMPLIANCE_STORAGE_BACKEND`) over the untouched SQLite path and a new DynamoDB backend, so the existing test suite runs unchanged. `app/main.py`'s auth gained an additive RS256/JWKS path for Cognito tokens alongside the existing HS256 path. Lambda bundling avoids Docker (not available in the build environment) via a pip-install-to-directory step instead.

Deliberately not run: `cdk deploy` — that provisions real, billable AWS resources and needs real credentials.

Also added `docs/problem_statement.md`, a standalone write-up of who has the compliance-gating problem this tool solves and why, separate from the technical design docs.

## Vendor payment/banking detail-change verification (`PROC-VENDOR-PAYMENT-CHANGE-001`)

Closed a real gap: none of the other controls verified that a vendor's payment destination hadn't been fraudulently redirected — the classic business-email-compromise fraud vector. A changed-but-unverified detail returns `insufficient_evidence`; a failed verification blocks the payment at CRITICAL risk; a verified change still routes to review. Cited Barbados's Computer Misuse Act (computer-related fraud) and the National Payment System Act, 2021.

## Gifts, hospitality & entertainment / anti-bribery (`PROC-GIFTS-HOSPITALITY-001`)

Gifts/hospitality/entertainment below a threshold auto-close; above it — or at any amount when the counterparty is a government official — require pre-approval; a denial blocks the transaction. Cited the Prevention of Corruption Act, 2021 (Barbados), which covers both public-official and private-sector bribery. Reused the existing `ApprovalRecord` evidence type rather than adding a new one.

## Part-time contract vendor control + regulatory citation framework

Added `PROC-PART-TIME-CONTRACT-001` for worker-misclassification risk on part-time/temporary vendor engagements — a real compliance exposure distinct from ordinary procurement. Also added `RuleMetadata.policy_references`, closing a traceability gap (control rules previously had no way to cite what regulation or internal policy they actually enforced), and `validate_no_internal_policy_conflicts()`, which structurally blocks a rule catalog from loading if an internal threshold is ever looser than a declared regulatory floor. Backed four of the six controls that existed at the time with real, researched Barbados/Caribbean sources; left two honestly internal-policy-only rather than inventing a citation.

## Escalation notification routing + dashboard summary

Added `GET /dashboard/summary` (per-control decision breakdown, triggered-signal frequency, active review queue snapshot) and `escalation_recipients` — a per-decision, per-risk-band computed field for which stakeholder groups (Procurement/Legal/Finance) should be notified, driven by a versioned policy in each rule catalog rather than hardcoded.

## Expense receipts, conflict of interest, jurisdiction due-diligence

Added `PROC-EXPENSE-RECEIPT-001` (itemized receipt + amount-reconciliation requirements), `PROC-VENDOR-COI-001` (conflict-of-interest disclosure and clearance — a cleared conflict still routes to review rather than auto-closing), and `PROC-INTL-VENDOR-001` (enhanced due diligence for high-risk jurisdictions, driven by a versioned country-code list rather than a caller-supplied risk flag).

## Pivot to a vendor due-diligence gate

Replaced the employee-conduct domain (harassment, discrimination, client treatment, international governance) with vendor spend gating: `PROC-SPEND-APPROVAL-001` and `PROC-VENDOR-DUEDILIGENCE-001`. Reused the existing FastAPI + JWT/RBAC + deterministic rule engine + append-only SQLite audit trail scaffold as-is.

Fixed two real bugs found while reviewing the prior implementation:
- `DecisionState.HUMAN_REVIEW_REQUIRED` didn't exist, so submitting or reopening a review crashed with `AttributeError`.
- `GET /reports/summary` built its response with field names that didn't match the model, so the endpoint 500'd on every call.

The test suite was also fully rewritten — the previous one targeted an even earlier domain and didn't exercise the shipped code at all.

## Verification notes

A running theme throughout: changes were verified directly, not just written and assumed correct.

- The whole app has been run live and exercised through a browser/JS console against a real server — `/evaluate`, `/reviews/queue`, `/reviews/{case_id}/assign`, and `/dashboard/summary` all confirmed working end-to-end, not just unit-tested in isolation.
- The DynamoDB storage backend and the Cognito RS256/JWKS auth path were exercised directly: a locally-signed RS256 token with a `cognito:groups` claim (no `role` claim) was correctly authorized, and a token signed with the wrong key was correctly rejected with 401.
- `cdk synth --strict` succeeds on both AWS stacks, and the built Lambda package was inspected directly to confirm the optional LLM agent scaffolding never leaks into the AWS deployment.
- `python -m pytest tests/test_api.py` (47 tests) passes throughout against the SQLite backend, regardless of the storage/auth/AWS work layered on top — the suite never sets `COMPLIANCE_STORAGE_BACKEND`, so it stays on the original, unmodified path.
