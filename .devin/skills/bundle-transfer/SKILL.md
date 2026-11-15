---
name: bundle-transfer
description: Prepare or import offline feature branches using fixed-name Base64 Git bundles between machines without GitHub access.
---

# Bundle transfer

Use `bash script/prepare-bundle.sh [branch] [base]` on the source. Defaults: current branch and main. Requires Bash, Python 3 and Git, no third-party Python packages.

Copy `bundle.b64` or all `bundle.b64.1`, `.2`, ... to the target. Names are fixed; one branch per transfer. Each chunk has at most 1000 lines of 76 Base64 characters. Never commit transfer artifacts.

On the target run `bash script/unpack-bundle.sh [branch] [directory]`. Branch is auto-detected when omitted. Use the bundle's actual branch name, not a rename. The required base commit must already exist; update main first if verification reports missing prerequisites.

Protections:
- Source and target trees must be clean, including untracked non-ignored files.
- Export refuses existing fixed-name outputs; ask the user to move them aside before another export. Never delete previous deliveries automatically.
- Base64 input takes precedence over an old decoded bundle. Single and numbered inputs together are rejected. Use a fresh transfer directory for each import to avoid mixing deliveries.
- Numbered chunks must start at 1 and be contiguous; ordering is numeric, not lexical.
- Strict Base64 decoding and Git verification must succeed before branch changes.
- Import rejects main, multiple branch heads, mismatched branch names, and local branches ahead of or divergent from the incoming branch. It only creates a branch or fast-forwards it, including when already checked out.
- If both machines committed independently, stop and reconcile explicitly. Never reset or force-checkout to make import succeed.

Agents never push or open/merge PRs. The user runs `git push -u origin <branch>` and `gh pr create` after importing. CI is the only test gate. Legacy bundle-branch scripts use a different format and are not inputs to this workflow.

Bootstrap: when the target has not yet received these scripts, import the provided decoded bundle with `git bundle verify`, `git fetch ./bundle.bundle refs/heads/<branch>`, then `git switch -c <branch> FETCH_HEAD` for a new branch. If the branch exists, inspect it and fast-forward explicitly; never overwrite it.
