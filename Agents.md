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
- Do not move to the next step until the current one passes tests.
- Use workflows: `/new-feature`, `/fix-bug`, `/add-tests`.

## 4. Subagent Strategy

- Use subagents liberally to keep main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.
- Summarize between steps to prevent context drift across long conversations.

## 5. Verification Before Done

- Never mark a task complete without proving it works.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"
- Run `make test` and `make lint`, check logs, demonstrate correctness.

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

## 10. Branch-Based Development

- **All changes must be made in feature/fix branches.** Never push directly to `main`.
- A single branch may contain multiple bug fixes or multiple features — grouping related work is fine.
- Before starting any work, create or switch to a branch (e.g. `feat/...`, `fix/...`, `chore/...`).
- **Always create new branches from `main`** — switch to `main` and pull latest changes (`git checkout main && git pull`) before creating the branch.
- Merge to `main` only via pull request after verification (`make test` + `make lint` pass).
- If the current branch is `main`, **stop and create a new branch** before making any commit.

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

## Guardrails

### ALWAYS
- Work on a feature/fix branch — never commit directly to `main`.
- Include context loading (Rule 1) before any non-trivial task.
- Run `make test` and `make lint` before marking any task complete.
- Write or update tests alongside every code change.
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
- Delete tests without explicit user approval.
- Skip the spec update for new features.
- Commit code that fails `make test` or `make lint`.
- Hardcode IP addresses, API keys, or credentials — use config/env.

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
| **Personal Mac** | Test & validate | `git clone`, `make install`, `make test`, `make lint`. Push when green. |
| **GitHub Actions** | CI | Lint → test. Triggered on push/PR to `main`. |
| **Mini PC** (Windows + WSL2) | Production | `git pull && docker compose build && docker compose up -d`. Local build, no registry. |

### Deployment flow
```
Work laptop → push → GitHub → PR → Mac validates → merge to main
    → GitHub Actions: lint + test
    → Mini PC: git pull && docker compose build && docker compose up -d
```

### NEVER on work laptop
- Run `make test`, `make lint`, `poetry install`, or `docker build`.
- These commands are reserved for the Mac or CI.

## Core Principles

- **Simplicity First** — Make every change as simple as possible. Impact minimal code.
- **No Laziness** — Find root causes. No temporary fixes. Senior developer standards.
- **AI output is a draft, not an answer** — Always verify. Models sound certain while being wrong.
