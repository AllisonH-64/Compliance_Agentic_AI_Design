# Reflection

An honest look back, and a self-review against the AWS Well-Architected pillars — written for the capstone, not for the code to read.

## What broke, and what I did about it

**The LLM agent was completely broken when I actually tested it, not just read it.** `orchestrator.py`/`router.py`/`tools.py` existed as scaffolding but had never been mounted or exercised: `tools.py` called endpoints that didn't exist (`/investigations/queue` instead of `/reviews/queue`), sent the wrong payload key (`investigator` instead of `reviewer_id`), and `orchestrator.py` compared a decision's risk band against `HIGH_SEVERITY_BANDS = {"HIGH", "CRITICAL"}` using the wrong field name and the wrong case — the API returns lowercase `risk_band`, not uppercase `severity_band` — so the human-confirmation gate for high-risk cases could never actually trigger. None of this showed up from reading the code; it only surfaced by running it against a live server and watching it fail. Lesson: a code review is not a test.

**I built the entire engine before checking it against AWS usage at all.** The domain, the rule engine, the API, the tests — all of it existed as a purely local FastAPI app before I checked it against the capstone rubric and found zero cloud usage. The AWS deployment layer, CI/CD pipeline, and cost governance were all retrofitted afterward, under real time pressure, rather than planned in from day one. It worked out — the retrofit is synth-verified and sound — but the honest version of this story is "found a gap, then closed it," not "planned for breadth from the start." If I did this again, I'd sketch the AWS shape in week one, even before writing the first rule catalog.

**The success metric came last, not first.** Decision latency (p50 11.4ms / p95 12.7ms) wasn't measured until I was asked what number proves the system works — well after the engine was "done." That's backwards. A number you only check once, at the end, can't catch a regression; instrumenting it from day one would have.

**Windows cost real debugging time on problems that had nothing to do with the code.** Orphaned listening sockets left behind by `uvicorn --reload`'s two-process architecture, stdout buffering that hid live logs when redirected to a file, and Console QuickEdit Mode silently pausing the server when clicked into — none of it was a code defect, but diagnosing "is this a stale-code bug or an environment bug" ate real time before the actual cause (leftover processes from earlier runs) became clear. The fix was environmental, not clever: default `--reload` off, and a single-process demo launcher (`run_demo.py`) that can't leave a second process behind because there isn't one.

**The domain itself moved three times before it landed.** This repo was, in order, a procurement idea, then a gifts/hospitality-specific one, then a full employee-conduct compliance system, before settling on vendor due-diligence. `docs/architecture.md`'s banner and `CHANGELOG.md` are both honest about this rather than presenting the final shape as if it were the first idea.

## What I'd design differently

- Plan the AWS layer, CI/CD, and cost governance from the start, not as a rubric-driven retrofit.
- Add structured logging to the app itself before calling observability solved — the CloudWatch alarms are real, but they watch a service that logs nothing structured today. That's the single biggest gap left.
- Tighten CORS (`allow_origins=["*"]`) before any real frontend exists, rather than leaving it open because none exists yet.
- Instrument the success metric on day one, not as a final step.

## What's next

Run the actual `cdk deploy` closer to demo day, wire `escalation_recipients` to a real outbound channel, confirm the Integrity in Public Life Act's enactment status for the conflict-of-interest control, and record the live demo.

## Six Pillars self-review

| Pillar | Honest answer |
|---|---|
| **Operational Excellence** | *If this broke at 3am, would I know?* Partially — CloudWatch alarms exist (API errors/throttles/p99 duration, export-Lambda iterator age) but have **never fired for real**, because nothing is deployed yet. An alarm that's never fired is a claim, not a proof. *Could I deploy a fix without manual steps?* Yes — push to `main` and CI/CD deploys via OIDC, tests gate it — once the one-time bootstrap is done. |
| **Security** | *Is anything public that shouldn't be?* No — S3 blocks all public access, DynamoDB isn't exposed, and `/health` is the only unauthenticated route, deliberately (a liveness check that itself needs a token defeats the point). *Does every permission have a reason?* Yes — IAM is granted via `grant_read_write_data()`/`grant_write()`, no wildcards; the GitHub OIDC deploy role can only `sts:AssumeRole` the CDK bootstrap roles, nothing else. Weakest point: CORS still allows all origins — acceptable only because no frontend exists yet, and documented as such. |
| **Reliability** | *What's the single point of failure?* The audit-export Lambda's DynamoDB Streams consumer — if it lags or fails, the S3 audit archive falls behind. It can't lose a decision, though: `/evaluate` writes the decision and its history record to DynamoDB synchronously, before the stream event ever fires. The export pipeline is decoupled and eventually consistent by design, not by accident. |
| **Performance Efficiency** | *What's the slowest part, and do I know that from measurement or assumption?* Measured: `/evaluate` runs p50 11.4ms / p95 12.7ms locally (SQLite, single warm process). Unmeasured: the AWS-deployed path — cold starts and network hops are a real unknown until it's actually deployed. |
| **Cost Optimization** | *What does this cost per month and per request?* Everything is pay-per-request — Lambda invocations, DynamoDB `PAY_PER_REQUEST`, API Gateway — no idle compute anywhere. A $25/month budget alerts at 80% actual and 100% forecasted. Actual per-request cost is still unmeasured, since nothing is deployed; the budget is a ceiling, not yet a measurement. |
| **Sustainability** | *Am I storing data forever that nobody needs?* Yes, deliberately — the audit tables and S3 archive use `RemovalPolicy.RETAIN` with no lifecycle or expiry, because an audit trail that can be silently deleted isn't an audit trail. That's a considered tradeoff, not an oversight, but it does mean storage grows unbounded. A real production version of this would add a lifecycle policy (e.g. S3 Glacier after N years), not delete anything. |

**The weakest answer is Operational Excellence's alarm claim** — an alarm that's never fired isn't proven, and the only real fix is deploying for real and watching one actually trip. That's the one item on this whole list that can't be closed by more local work; it's the reason the AWS bootstrap is still deliberately on the calendar for closer to demo day rather than done already.
