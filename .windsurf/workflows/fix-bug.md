---
description: Structured workflow for diagnosing and fixing a bug — context, diagnose, fix, regression test.
---

## Step 1: Context

Gather all available information:
- Read `@README.md` and `@Agents.md` for project rules.
- Read the error message, stack trace, or bug description provided by the user.
- Identify and read the relevant source files and tests.

Summarize your understanding of the bug before proposing a fix.

## Step 2: Diagnose

1. Explain what the code does step by step in the area of the bug.
2. List the most likely failure cases.
3. Identify the root cause — do NOT jump to a fix yet.
4. If the root cause is unclear, add diagnostic logging and ask the user to reproduce.

**Rule: Do NOT propose code changes until the root cause is identified.**

## Step 3: Plan the Fix

1. Describe the minimal fix needed — prefer upstream fixes over downstream workarounds.
2. Call out any tradeoffs or side effects.
3. Present the plan for approval.

## Step 4: Implement

1. Apply the fix — keep it as small as possible.
2. Write a regression test that would have **failed before the fix** and passes after.

## Step 5: Verify

// turbo
Run the test suite:
```sh
make test
```

// turbo
Run the linter:
```sh
make lint
```

## Step 6: Document

1. Summarize the root cause and the fix.
2. Update `tasks/lessons.md` with the pattern if the bug reveals a recurring mistake.
3. If the bug exposed a gap in specs, update them.

**Reset rule:** If you've proposed 2 fixes that don't work, STOP. Summarize what you've tried, restate the problem with better context, and start fresh reasoning. Do not keep iterating on the same broken approach.
