---
description: Orchestrate work across multiple GitHub issues in one command — auto-decide parallel vs sequential, isolate each in a git worktree, implement, push, watch CI, merge in order.
---

## When to use

Trigger this from the **orchestrator window** (the main `NukiBlinker` checkout on
`main`) with one instruction, e.g.:

> "trabaja las issues 140 141 142" / "lanza el trabajo en las issues X Y Z" / "/orchestrate 140 141 142"

The orchestrator (Cascade in this window) drives everything end to end: batching,
worktree isolation, implementation, push, CI loop, and ordered merges.

### Honest model note
Cascade is a single agent per conversation, so within ONE window issues are executed
**sequentially by the orchestrator**, each **isolated on its own worktree+branch**.
That "parallelism" is logical: independent issues get independent branches mergeable
in any order; dependent/overlapping issues are chained.

### Two ways to run

- **Sequential (this window)**: follow Steps 1–7 below. One Cascade does everything,
  one issue at a time. Best for dependent issues (a shared-file chain) and for small
  batches where wall-clock time doesn't matter.
- **Real parallel (multi-window)**: for independent issues, use the launcher
  `script/orchestrate-parallel.ps1` (`.sh` on Linux/WSL2). It creates a worktree +
  branch + task brief per issue and **opens one Windsurf window per issue**. In each
  new window you type a single command — **`/orchestrate-run`** — and that agent
  reads its `.orchestrate-task.md` and runs autonomously (Cascade has no API to
  auto-inject the prompt, so this one paste is required). With `-Wait` the launcher
  **polls GitHub until every PR is green**; with `-Merge` it then squash-merges in
  issue order, rebasing the rest. Example:

  // turbo
  ```powershell
  .\script\orchestrate-parallel.ps1 -Issues 140,141,142 -Wait
  ```

  Use this only for issues with **disjoint file sets**; chain dependent/overlapping
  issues sequentially instead (see Step 2 batching).

## Step 1: Gather the issues

For each issue number, read its scope and labels:

// turbo
```powershell
gh issue view <N> --repo nicdobler/NukiBlinker --json number,title,body,labels
```

Classify each as **feature** or **bug** from its labels/title (drives whether to
follow `/new-feature` or `/fix-bug`).

## Step 2: Decide parallel vs sequential (batching)

For each issue, estimate the **set of files/modules** it will touch (use
`code_search` + the issue body). Then build an execution plan:

- **Parallel-safe batch**: issues whose estimated file sets are **disjoint** and
  have **no logical dependency**. Each gets its own worktree+branch from
  `origin/main`; they may be merged in any order.
- **Sequential chain**: issues that **overlap files** or **depend** on another.
  Order them; each later issue branches from `main` *after* the earlier one is
  merged (or is rebased on it).

Present a concise plan (batches + order + branch names) and proceed automatically
unless the user objects. Append the plan to `tasks/todo.md`.

## Step 3: Create a worktree per issue

For each issue in the current batch:

// turbo
```powershell
.\script\worktree.ps1 -Action new -Branch <type>/<N>-<slug>
```

Branch naming: `feat/<N>-<slug>` for features, `fix/<N>-<slug>` for bugs.

## Step 4: Implement each issue in its worktree

For each worktree, operate with that folder as the working directory and follow
the matching loop:
- Features → `/new-feature` (spec → plan → implement → tests).
- Bugs → `/fix-bug` (diagnose → root cause → fix → regression test).

Keep changes scoped to that issue's files. Commit inside the worktree.

## Step 5: Push + open PR + autonomous CI loop

For each branch:

// turbo
```powershell
git -C ..\NukiBlinker-wt\<type>-<N>-<slug> push -u origin <type>/<N>-<slug>
```

```powershell
gh pr create --repo nicdobler/NukiBlinker --title "<type>(#<N>): <title>" --body "Closes #<N>. ..."
gh pr checks <PR> --repo nicdobler/NukiBlinker --watch --interval 15
```

If CI fails: read logs, diagnose root cause, fix in the worktree, re-push, repeat.
**Reset rule (Rule 7)**: after 2 failed attempts on the same failure, STOP and re-plan.

## Step 6: Merge in order, rebase the rest

Merge one branch at a time (respect the session's **wrap-up mode**, Rule 10a):

```powershell
gh pr merge <PR> --squash --repo nicdobler/NukiBlinker
```

After each merge, rebase every remaining worktree on the updated `main` to surface
conflicts early:

// turbo
```powershell
git -C ..\NukiBlinker-wt\<other> fetch origin; git -C ..\NukiBlinker-wt\<other> rebase origin/main
```

For sequential chains, only branch/implement the next issue after its predecessor
is merged.

## Step 7: Cleanup + document

For each merged branch:

// turbo
```powershell
.\script\worktree.ps1 -Action remove -Branch <type>/<N>-<slug>
```

Then in the orchestrator window:

// turbo
```powershell
git checkout main; git pull; git fetch --prune
```

Delete merged local branches, update `CHANGELOG.md` `[Unreleased]`, and mark the
issues done in `tasks/todo.md`. Report a final status table: issue → branch → PR →
CI → merged.
