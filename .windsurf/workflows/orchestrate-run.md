---
description: Execute the orchestrated task brief in this worktree (spawned by orchestrate-parallel)
---

You are a Cascade session running in an **isolated git worktree** that was spawned by
`script/orchestrate-parallel.ps1` (or `.sh`). Your job is to deliver ONE issue end to end,
fully autonomously, and stop short of merging.

## Step 1: Read the task brief

// turbo
```powershell
Get-Content .orchestrate-task.md
```

The brief names the **issue number**, the **branch** (already checked out here), the
**type** (feat/fix) and the title. If `.orchestrate-task.md` is missing, stop and tell the
user this window was not launched by the orchestrator.

## Step 2: Load context

Read the issue and the repo conventions before changing anything:

// turbo
```powershell
gh issue view <N> --repo nicdobler/NukiBlinker
```

Then read `README.md`, `Agents.md`, the relevant `specs/`, and the source + tests you will touch.

## Step 3: Implement on THIS branch

Follow the matching workflow:
- **feat** → `/new-feature` (spec → plan → implement → tests).
- **fix**  → `/fix-bug` (diagnose → root cause → fix → regression test).

Keep changes scoped to this issue's files to minimise cross-branch merge conflicts.
Write/adjust tests and update docs/specs/CHANGELOG alongside the code.

## Step 4: Push + open a PR

// turbo
```powershell
git push -u origin <branch>
```

```powershell
gh pr create --repo nicdobler/NukiBlinker --base main --head <branch> --title "<type>(#<N>): <title>" --body "Closes #<N>. ..."
```

## Step 5: Drive CI to green (autonomous loop)

```powershell
gh pr checks <PR> --repo nicdobler/NukiBlinker --watch --interval 20
```

If CI fails: read the failing job logs, diagnose the root cause, fix in this worktree,
re-push, and repeat. **Reset rule (Rule 7):** after 2 failed attempts on the same failure,
STOP and re-plan.

## Hard rules

- **Never merge** and **never touch `main`** — the orchestrator merges all branches in order.
- **Never commit** `.orchestrate-task.md` (it is git-ignored; leave it untracked).
- When CI is green, report the **PR number** and final status. The orchestrator window is
  polling GitHub and will wrap up once every branch is green.
