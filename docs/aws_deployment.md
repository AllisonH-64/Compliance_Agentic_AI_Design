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
- **`VendorGateGovernanceStack`** (account-level, deployed once by hand — not by CI, and not part of the two stacks above):
  - A GitHub OIDC provider + an IAM role (`github-actions-vendor-gate-deploy`) that GitHub Actions assumes to deploy the other two stacks. No long-lived AWS access keys exist anywhere in this repo or its secrets. The role's trust policy is scoped to `repo:AllisonH-64/Compliance_Agentic_AI_Design:ref:refs/heads/main` — a fork or a feature-branch workflow run cannot assume it. The role itself holds no service permissions; it can only `sts:AssumeRole` the roles `cdk bootstrap` already created, which is the standard least-privilege pattern for GitHub OIDC + CDK.
  - An AWS Budget (`MonthlyCostBudget`) with email alerts at 80% of actual spend and 100% of forecasted spend.

## CI/CD

`.github/workflows/ci.yml` runs the test suite and `cdk synth --strict` (no AWS credentials needed) on every pull request. `.github/workflows/deploy.yml` runs the same checks and then `cdk deploy` for `VendorGateDataStack`/`VendorGateApiStack` on every push to `main`, authenticating via OIDC against `VendorGateGovernanceStack`'s deploy role — no stored AWS keys, no manual `cdk deploy` from a laptop once this is set up.

**One-time bootstrap** (by hand, with your own AWS credentials — this is the only manual AWS step in the whole pipeline):

```bash
cd infra
pip install -r requirements.txt
cdk bootstrap aws://<account-id>/<region>

BUDGET_ALERT_EMAIL=you@example.com cdk deploy VendorGateGovernanceStack
# copy the GitHubActionsDeployRoleArn output
```

Then, in the GitHub repo (Settings → Secrets and variables → Actions):
- Secret `AWS_DEPLOY_ROLE_ARN` = the role ARN from that output
- (Optional) Variable `AWS_REGION` if not `us-east-1`

From then on, a push to `main` that touches `app/`, `data/rules/`, `infra/`, or `lambda_handler.py` deploys automatically. `GovernanceStack` itself is deliberately excluded from what CI redeploys — re-provisioning the role that trusts CI, from inside CI, is the kind of thing you want a human doing on purpose, and it doesn't change often enough to need it.

If the AWS account already has a GitHub OIDC provider from another project, `iam.OpenIdConnectProvider(...)` in `infra/governance_stack.py` will fail with "already exists" — swap it for `iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(...)` against the existing provider's ARN instead.

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

## Cost and teardown

Everything here is pay-per-request or free-tier-sized — there's no always-on compute:

| Resource | Pricing model | Expected cost at demo traffic |
|---|---|---|
| Lambda (API + audit-export) | Per-invocation + duration | Fractions of a cent for a handful of demo requests |
| DynamoDB (4 tables) | On-demand (`PAY_PER_REQUEST`) | Near-zero at low read/write volume; no idle charge |
| API Gateway (HTTP API) | Per-request | ~$1/million requests |
| S3 (audit bucket) | Per-GB stored | Negligible at this data volume |
| Cognito | Free under 10,000 MAUs | $0 for a demo |
| CloudWatch (logs + alarms) | Per-GB ingested + per-alarm | A few cents/month |
| Budget alert (`VendorGateGovernanceStack`) | Set to $25/month by default (`BUDGET_MONTHLY_LIMIT_USD`) | Alerts at 80% actual / 100% forecasted, before it's a surprise |

**Teardown:** `cdk destroy VendorGateApiStack` removes the Lambdas, API Gateway, and their log groups/alarms cleanly (`RemovalPolicy.DESTROY`) — nothing there is stateful. `VendorGateDataStack` and `VendorGateGovernanceStack` are `RemovalPolicy.RETAIN` throughout on purpose (destroying the stack doesn't delete the tables, bucket, user pool, or budget) — deleting those, if genuinely intended, is a separate manual step in the console or CLI, not a side effect of `cdk destroy`. Redeploying afterward is one command (`cdk deploy --all`, or a push to `main` once CI/CD is wired up) since everything is defined in code — nothing here was clicked into existence.

**Success signal for this piece specifically:** I'll know the CI/CD + budget work is working when (a) a push to `main` shows a green `deploy.yml` run in the Actions tab that used a short-lived OIDC token, not a stored key, and (b) the budget alert email actually arrives — tested by temporarily setting `BUDGET_MONTHLY_LIMIT_USD` to something below current month-to-date spend and confirming the ACTUAL notification fires, then setting it back.

## Known limitations / honest gaps

- `list_decisions()`/`list_review_queue()` on the DynamoDB backend use a full table `Scan`. Fine at this MVP's traffic; a GSI (e.g. on `review_required`) is a documented follow-up if volume grows — consistent with the "honest caveat, not invented certainty" approach used throughout this repo's other docs (see `docs/mvp.md`'s regulatory-sourcing section for the same pattern).
- CloudWatch alarms have no action (SNS topic/subscription) wired by default — add one once there's an actual on-call destination; wiring a fake email address would be worse than leaving it unconfigured.
- CORS on the HTTP API currently allows all origins (`allow_origins=["*"]`) since there's no frontend yet to scope it to — tighten this before any browser-based client exists.
- This was verified with `cdk synth --strict` on all three stacks (produces valid, correctly-wired CloudFormation) but **not deployed** to a real AWS account — that provisions real, billable resources and needs real credentials, which wasn't something to do without explicit confirmation. Everything above is what `cdk deploy` would create, not a claim that it's currently running.
- Corollary: `.github/workflows/deploy.yml` has never actually run against real AWS credentials either — it exists and will `synth`/`deploy` correctly once `AWS_DEPLOY_ROLE_ARN` is set, but until the one-time bootstrap above happens, no green run in the Actions tab has proven it end to end. Don't claim this pipeline "works" in a demo until you've watched it deploy at least once.
