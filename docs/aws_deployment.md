# AWS Deployment Layer

This is the real, synth-verified infrastructure putting the vendor due-diligence gate on AWS — it supersedes the sketch in `docs/architecture.md` Section 21/22 for everything described here. The application code is unchanged between local and AWS deployment; only `COMPLIANCE_STORAGE_BACKEND` and a handful of auth-related environment variables differ.

## What's actually built

Two CDK (Python) stacks under `infra/`:

- **`VendorGateDataStack`** (stateful — `RemovalPolicy.RETAIN` throughout, so a `cdk destroy` can never silently wipe data):
  - 4 DynamoDB tables mirroring the SQLite schema: `decisions`, `reviews` (current state), `decision_history`, `review_history` (append-only, streams enabled).
  - An S3 bucket for the immutable audit export (versioned, block-public-access, SSE).
  - A Cognito User Pool + one App Client (no secret) + 4 Groups (`employee`, `compliance_analyst`, `compliance_manager`, `auditor`) — named to match `UserRole` in `app/models.py` exactly.
- **`VendorGateApiStack`** (stateless, depends on the data stack via cross-stack references):
  - The API Lambda — the existing FastAPI app, unmodified, wrapped by Mangum (`lambda_handler.py`) as a single Lambdalith rather than one function per route.
  - An HTTP API (API Gateway v2) with a native JWT authorizer pointed at the Cognito User Pool — no custom Lambda authorizer needed.
  - An audit-export Lambda subscribed to the two history tables' DynamoDB Streams, writing every new decision/review event to S3 as `s3://{bucket}/{table}/dt={date}/{event_id}.json`.
  - CloudWatch log groups (1-month retention) and alarms (API errors, throttles, P99 duration; export Lambda iterator age).

## How auth actually works

The app's own JWT verification (`app/main.py`) didn't get replaced by Cognito — it was extended to trust Cognito as the token issuer:

- Locally / in tests: `COMPLIANCE_AUTH_SECRET` (HS256, shared secret) — unchanged, exactly as before.
- On AWS: `COMPLIANCE_AUTH_JWKS_URL` is set to the User Pool's JWKS endpoint, so the app verifies RS256-signed Cognito tokens against the pool's public keys instead of a shared secret (Cognito never hands out a static secret).
- Role resolution: a token's `role` claim is used if present (local/test tokens); otherwise the app falls back to the first entry in the `cognito:groups` claim (real Cognito tokens) — so a user's Cognito Group *is* their `UserRole`, no pre-token-generation Lambda trigger required.

This was verified directly, not just assumed: a locally-generated RS256 token with `cognito:groups: ["compliance_manager"]` and no `role` claim was accepted and correctly authorized against a role-gated endpoint, and a token signed with the wrong key was correctly rejected with 401 (see the commit history for the verification script).

## Deploying

**Prerequisites:** Node.js ≥ 20 (for the CDK CLI via `npx`), Python 3.11+, an AWS account and credentials (`aws configure` or SSO).

Lambda bundling deliberately avoids CDK's usual Docker-based bundling (`Code.from_asset(..., bundling=...)`) since Docker isn't assumed to be available — `infra/app.py`'s `build_lambda_asset()` instead pip-installs `infra/lambda_requirements.txt` (the Lambda's runtime-only deps — not the repo's top-level `requirements.txt`, which also carries pytest/httpx/uvicorn the Lambda never needs) for the `manylinux2014_x86_64` / Python 3.13 platform into `infra/build/lambda_package`, then copies `app/`, `lambda_handler.py`, and `data/rules/` in. This runs automatically as part of `cdk synth`/`cdk deploy` — no separate manual build step. If Docker is available and preferred, swap this for a `BundlingOptions` block instead.

```bash
cd infra
pip install -r requirements.txt
cdk bootstrap aws://<account-id>/<region>   # once per account/region
cdk synth --strict                          # validate — no AWS calls beyond account/region lookup
cdk diff                                    # review before deploying
cdk deploy --all
```

After deploying, create a first `compliance_manager` user and add them to that Cognito Group (`aws cognito-idp admin-create-user` / `admin-add-user-to-group`) — self-sign-up is disabled by design (`DataStack`'s `self_sign_up_enabled=False`), since account provisioning should go through a manager, not open registration.

## Known limitations / honest gaps

- `list_decisions()`/`list_review_queue()` on the DynamoDB backend use a full table `Scan`. Fine at this MVP's traffic; a GSI (e.g. on `review_required`) is a documented follow-up if volume grows — consistent with the "honest caveat, not invented certainty" approach used throughout this repo's other docs (see `docs/mvp.md`'s regulatory-sourcing section for the same pattern).
- CloudWatch alarms have no action (SNS topic/subscription) wired by default — add one once there's an actual on-call destination; wiring a fake email address would be worse than leaving it unconfigured.
- CORS on the HTTP API currently allows all origins (`allow_origins=["*"]`) since there's no frontend yet to scope it to — tighten this before any browser-based client exists.
- This was verified with `cdk synth --strict` (produces valid, correctly-wired CloudFormation) but **not deployed** to a real AWS account — that provisions real, billable resources and needs real credentials, which wasn't something to do without explicit confirmation. Everything above is what `cdk deploy` would create, not a claim that it's currently running.
