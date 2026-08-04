# Workspace Agent Instructions

This workspace is a FastAPI compliance agent for employee conduct and workplace governance. Treat the repository as a deterministic compliance system, not a generic app.

## What this workspace does

- Evaluates conduct and compliance incidents for harassment, discrimination, client treatment, and international governance.
- Uses versioned rule catalogs under `data/rules/` and deterministic evaluation logic in `app/engine.py`.
- Persists decisions and review state in SQLite through `app/storage.py`.
- Exposes the API from `app/main.py` and validates behavior with `tests/test_api.py`.

## Operating rules

- Read `README.md` and the relevant `docs/` files before changing behavior.
- Prefer small, local edits that preserve deterministic rule evaluation.
- Update tests whenever a change affects evaluation, review workflow, queue metrics, or auth.
- Keep public API behavior stable unless the request explicitly asks for a breaking change.
- Preserve auditability: avoid changes that weaken decision history, review history, or review-state tracking.
- When adding or changing rules, keep the catalog versioned and make the selection logic explicit.

## Validation expectations

- Run the narrowest relevant test slice after behavioral edits.
- If an edit touches auth, review lifecycle, queue metrics, or persistence, validate those flows directly.
- Favor deterministic checks over manual inspection when a test already exists.

## Style and review expectations

- Keep the implementation straightforward and readable.
- Update docs when the user-facing workflow, endpoint list, or compliance behavior changes.
- Do not refactor unrelated code while working on a focused request.