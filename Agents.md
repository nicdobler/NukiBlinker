## 0. Spec-Driven Development

Every non-trivial change (new feature, architectural change) **must** update specs *before* writing implementation code.

### Spec locations
- `specs/product-spec.md` — what & why (scope, workflow, non-goals)
- `specs/tech-spec.md` — how (architecture, data model, module design, CI)

### Workflow gate
1. Read the relevant spec section.
2. Draft the spec change (add/modify sections) and present it to the user.
3. Only after spec is committed, proceed to implementation.
4. After implementation, run the **Documentation Checklist** below.

### Documentation Checklist (after completing a feature/fix)

Run this checklist before marking any feature/fix as complete:

- [ ] **specs/product-spec.md** — Feature description, acceptance criteria
- [ ] **specs/tech-spec.md** — Architecture, data model, module design
- [ ] **README.md** — Features, commands, configuration
- [ ] **CHANGELOG.md** — Add entry under `[Unreleased]` section
- [ ] **GitHub Issues** — Update/close related issues
- [ ] **Tests** — New/updated tests pass (`make test` + `make lint`)

### When to skip
- Pure bug fixes, typo corrections, dependency bumps — no spec update needed.
- If unsure, default to updating the spec.

## 1. Context First

Before starting any non-trivial task, load context like you'd brief a teammate:
- Read `README.md` for project scope.
- Read `Agents.md` for coding rules and conventions.
- Read relevant specs (`specs/product-spec.md`, `specs/tech-spec.md`).
- Identify and read the source files and tests relevant to the task.

Summarize your understanding before proposing changes.

## 2. Plan First

- Enter plan mode for any task with 3+ steps or architectural decisions.
- If something goes sideways, STOP and re-plan — don't keep pushing.
- Use plan mode for verification steps, not just building.
- Write plan to `tasks/todo.md` with checkable items.
- Wait for user approval before implementing.

## 3. Small Steps + Test Alongside

- Implement one step at a time. Keep each change small and focused.
- Write or update tests **immediately** after each step — not later.
- Tests are validated in CI (not locally); push and let CI confirm before relying on a step.
- Use workflows: `/new-feature`, `/fix-bug`, `/add-tests`.

## 4. Subagent Strategy

- Use subagents liberally to keep main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.
- Summarize between steps to prevent context drift across long conversations.

### Parallel agents via git worktrees

- To run **multiple agents in parallel** on the repo, give each one its own
  **git worktree** (separate working dir, same `.git`) on its own branch from
  `origin/main`. This keeps their working trees isolated — conflicts only ever
  surface at merge time, never between folders.
- Worktrees live in the sibling folder `../NukiBlinker-wt/<branch-slug>` and are
  managed with `script/worktree.ps1` (`.sh` on Linux/WSL2): `new` / `list` / `remove`.
- Agents in worktrees **only edit and push** — no `.venv`, no local install,
  no local tests. CI is still the sole validation gate (Rule 5).
- One branch = one worktree = one agent. Assign distinct module/file areas to
  minimize merge conflicts. Merge one branch at a time, then rebase the rest.
- Use the `/worktree` workflow to drive this end to end.

## 5. Verification Before Done (CI is the gate)

- **CI is the only test environment.** Do not run `make test`, `make lint`, `poetry install`, or `docker build` on the work laptop.
- Prove work by pushing the branch and letting **GitHub Actions** run lint + test.
- Never mark a task complete until CI is green on the branch.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"

## 5a. Autonomous CI Loop

- After pushing, **work autonomously**: poll CI status, read failing job logs, diagnose the root cause, fix, and re-push.
- Iterate until CI is green without waiting for the user to prompt you.
- Apply the **Reset rule** (Rule 7): if 2 fix attempts fail on the same failure, STOP and re-plan.
- Report a concise status after each CI run (pass/fail + what you changed).

## 6. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Skip this for simple, obvious fixes — don't over-engineer.
- Challenge your own work before presenting it.

## 7. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding.
- Diagnose root cause first — do NOT jump to a fix.
- Point at logs, errors, failing tests — then resolve them.
- Write a regression test that would have failed before the fix.
- **Reset rule:** If 2 fix attempts fail, STOP. Summarize what you tried, restate the problem, and start fresh reasoning. Do not iterate on broken approaches.

## 8. Self-Improvement Loop

- After ANY correction from the user: update `tasks/lessons.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Ruthlessly iterate on these lessons until mistake rate drops.
- Review lessons at session start for relevant project.

## 9. Documentation

- After implementation, update `README.md` and specs to reflect changes.
- Keep documentation short and simple.
- **Session-start doc check**: At the beginning of every session, verify that `README.md`, `CHANGELOG.md`, `specs/product-spec.md`, and `specs/tech-spec.md` are consistent with the current codebase. Flag any drift and fix it before starting new work.

## 10. Branch-Based Development

- **All changes must be made in feature/fix branches.** Never push directly to `main`.
- A single branch may contain multiple bug fixes or multiple features — grouping related work is fine.
- Before starting any work, create or switch to a branch (e.g. `feat/...`, `fix/...`, `chore/...`).
- **Always create new branches from `main`** — switch to `main` and pull latest changes (`git checkout main && git pull`) before creating the branch.
- Merge to `main` only via pull request after **CI is green**.
- If the current branch is `main`, **stop and create a new branch** before making any commit.

## 10a. Wrap-Up Mode (per-session decision)

At the **start of each session**, ask the user which wrap-up mode applies (default to **Approval** if unspecified):

- **Auto wrap-up** — once CI is green, run `/wrap-up` autonomously (merge PR, switch to main, pull, clean up branches).
- **Approval** — once CI is green, stop and wait. The user reviews/approves the PR and tells you when to wrap up.

Never merge to `main` in Approval mode without explicit go-ahead.

## Task Management

1. **Plan First** — Append new plan to `tasks/todo.md` (never overwrite previous entries).
2. **Verify Plan** — Check in before starting implementation.
3. **Track Progress** — Mark items complete as you go.
4. **Explain Changes** — High-level summary at each step.
5. **Document Results** — Include branch name and PR number in the task header.
6. **Capture Lessons** — Update `tasks/lessons.md` after corrections.

`tasks/todo.md` is an **append-only log**. Each task gets a `---` separator, a heading with issue/feature title, and a `**Branch**: ... | **PR**: ...` line. Completed tasks stay as historical record.

## Workflows

Predefined step-by-step workflows:
- `.windsurf/workflows/*.md` — Windsurf format.

Available workflows:
- `/new-feature` — Full loop: context -> spec -> plan -> implement -> test -> review.
- `/fix-bug` — Diagnose -> root cause -> fix -> regression test -> document.
- `/add-tests` — Analyze coverage gaps -> generate tests -> verify.
- `/worktree` — Launch independent agents in parallel via git worktrees (one folder + branch per agent, push-only).

## Guardrails

### ALWAYS
- Work on a feature/fix branch — never commit directly to `main`.
- Include context loading (Rule 1) before any non-trivial task.
- Push the branch and confirm **CI is green** before marking any task complete.
- Write or update tests alongside every code change.
- Confirm the session's **wrap-up mode** (Rule 10a) before merging anything.
- Update specs after implementation if behavior drifted from the spec.
- **Update README.md** when adding/removing features or config options.
- **Update CHANGELOG.md** when merging PRs to `main`.
- Summarize what was done at the end of a session in `tasks/todo.md`.

### ASK BEFORE
- Adding a new dependency not already in `pyproject.toml`.
- Changing the callback payload contract or config schema.
- Modifying core interfaces (NukiClient, HueClient).
- Deleting or weakening existing tests.
- Architectural changes that affect the event pipeline.

### NEVER
- Push or commit directly to `main`. Always use a branch.
- Run `make test`, `make lint`, `poetry install`, or `docker build` on the work laptop — CI is the test environment.
- Delete tests without explicit user approval.
- Skip the spec update for new features.
- Merge a branch whose CI is not green.
- Hardcode IP addresses, API keys, or credentials — use config/env.
- Merge to `main` in Approval wrap-up mode without explicit user go-ahead.

## Session Handoff

At the end of every session (or when context gets long), update `tasks/todo.md` with:
- What was completed.
- Decisions made and why.
- Open questions or blockers.
- Exact next steps.

This ensures the next session can pick up without context loss.

## Development Environments

| Environment | Role | What runs here |
|---|---|---|
| **Work laptop** (Windows) | Code only | Write code, push to GitHub. **No testing, no Poetry, no Docker.** |
| **GitHub Actions** | CI — the test gate | Lint → test. Triggered on push/PR to `main`. Sole validation environment. |
| **Mini PC** (Windows + WSL2) | Production | `git pull && docker compose build && docker compose up -d`. Local build, no registry. |

### Deployment flow
```
Work laptop → push branch → GitHub → CI (lint + test) → PR
    → CI green → merge to main (auto or after user approval)
    → Mini PC: git pull && docker compose build && docker compose up -d
```

### NEVER on work laptop
- Run `make test`, `make lint`, `poetry install`, or `docker build`.
- These commands are reserved for CI.
- Verification happens exclusively in GitHub Actions CI.

## Core Principles

- **Simplicity First** — Make every change as simple as possible. Impact minimal code.
- **No Laziness** — Find root causes. No temporary fixes. Senior developer standards.
- **AI output is a draft, not an answer** — Always verify. Models sound certain while being wrong.
