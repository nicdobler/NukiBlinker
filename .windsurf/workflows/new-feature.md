---
description: Full workflow for implementing a new feature — context, spec, plan, code, test, review.
---

## Step 1: Context

Read the project context before doing anything:
- Read `@README.md` for project scope.
- Read `@Agents.md` for coding rules and conventions.
- Read `@specs/product-spec.md` and `@specs/tech-spec.md` for current architecture.
- Identify which source files are relevant to the feature.

Summarize your understanding of the project and the relevant modules before proceeding.

## Step 2: Spec Update

Following Rule 0 (Spec-Driven Development):
1. Draft changes to `specs/product-spec.md` (what & why).
2. Draft changes to `specs/tech-spec.md` (how — architecture, data model, modules).
3. Present the spec diff to the user for approval.
4. Do NOT write implementation code until the spec is approved.

## Step 3: Plan

1. Break the feature into small, ordered implementation steps.
2. For each step, list: files to change, what changes, and edge cases.
3. Write the plan to `tasks/todo.md` with checkable items.
4. Present the plan for approval. Wait for "approved" before coding.

## Step 4: Implement (One Step at a Time)

For each step in the approved plan:
1. Explain what you are about to change.
2. Make the code change — keep it small and focused.
3. Write or update tests for that step immediately.
4. Mark the step complete in `tasks/todo.md`.

Do NOT move to the next step until the current one is verified.

## Step 5: Test

// turbo
Run the full test suite:
```sh
make test
```

If any test fails, fix it before proceeding.

## Step 6: Lint

// turbo
Run the linter:
```sh
make lint
```

Fix any issues before proceeding.

## Step 7: Review & Document

1. Summarize all changes by file — explain the logic in plain language.
2. List what could break and how the tests cover it.
3. Update `README.md` if the feature is user-facing.
4. Verify specs still match the implementation; fix any drift.
