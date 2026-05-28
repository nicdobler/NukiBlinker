---
description: Generate or improve tests for existing code — unit tests, edge cases, regression tests.
---

## Step 1: Context

- Read `@Agents.md` for testing conventions.
- Read the target source file(s) that need tests.
- Read existing tests in `tests/` to understand the test style and fixtures used.

## Step 2: Analyze Coverage Gaps

1. List the public functions/methods in the target module.
2. Check which ones already have test coverage.
3. Identify gaps: untested functions, missing edge cases, missing error paths.

## Step 3: Generate Tests

For each gap, write tests following the existing style:
- **Happy path** — normal expected input and output.
- **Edge cases** — empty input, boundary values, None/null, malformed data.
- **Error paths** — invalid input that should raise exceptions or log warnings.

Use existing fixtures in `tests/fixtures/` when possible. Create new fixtures only if needed.

## Step 4: Run & Verify

// turbo
Run the tests:
```sh
make test
```

All new tests must pass. If any fail, fix the test (not the source code) unless a real bug is found.

## Step 5: Summary

1. List the tests added, grouped by module.
2. Note any real bugs discovered during test writing.
