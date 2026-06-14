---
description: Launch independent agents in parallel using git worktrees — one folder + branch per agent, push-only, CI validates.
---

## When to use

When you want to run **several agents in parallel** on this repo without them
stepping on each other's working tree. Each agent gets its own folder (worktree)
and its own branch from `origin/main`. Agents **only edit and push** — lint/test
run exclusively in CI (Rule 5).

Convention: worktrees live in a sibling folder `../NukiBlinker-wt/<branch-slug>`.

## Step 1: Define the tasks

For each agent, decide a branch name and a scope. To minimize merge conflicts,
give each agent a **distinct module/file area** whenever possible.

Example:
- Agent A -> `feat/web-ui-theme` (touches `nukiblinker/web_ui.py`)
- Agent B -> `fix/dedup-window` (touches `nukiblinker/dedup.py`)

## Step 2: Create a worktree per agent

From the main checkout, run once per agent (PowerShell on the work laptop):

// turbo
```powershell
.\script\worktree.ps1 -Action new -Branch feat/web-ui-theme
```

This fetches `origin`, creates the branch from `origin/main`, and checks it out
into `..\NukiBlinker-wt\feat-web-ui-theme`.

(Linux/WSL2 equivalent: `./script/worktree.sh new feat/web-ui-theme`.)

## Step 3: Launch the agent in its worktree

Point each agent at its worktree folder as the working directory, e.g.
`c:\Users\n97894\Code\NukiBlinker-wt\feat-web-ui-theme`. The agent follows the
normal rules (`/new-feature`, `/fix-bug`) **inside that folder**.

Each agent works on ONE task. Do not assign the same branch to two agents — git
forbids the same branch in two worktrees.

## Step 4: Push (no local tests)

Each agent commits and pushes its own branch. CI runs lint + test:

// turbo
```powershell
git -C ..\NukiBlinker-wt\feat-web-ui-theme push -u origin feat/web-ui-theme
```

## Step 5: Merge one at a time

Open a PR per branch. Merge to `main` only when **CI is green** and per the
session's wrap-up mode (Rule 10a). After each merge, rebase the other worktrees
to surface conflicts early:

```powershell
git -C ..\NukiBlinker-wt\fix-dedup-window fetch origin
git -C ..\NukiBlinker-wt\fix-dedup-window rebase origin/main
```

## Step 6: Clean up

When a branch is merged, remove its worktree:

// turbo
```powershell
.\script\worktree.ps1 -Action remove -Branch feat/web-ui-theme
```

List active worktrees anytime:

// turbo
```powershell
.\script\worktree.ps1 -Action list
```
