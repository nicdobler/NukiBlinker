---
description: Wrap up work — commit, push, create/merge PR, switch to main, pull, and clean up branches.
---

## Step 1: Stage and commit

If there are uncommitted changes, stage and commit them with a descriptive message.

```sh
git add -A && git status
```

// turbo
```sh
git commit -m "<type>: <description>"
```

Skip this step if the working tree is clean.

## Step 2: Push

// turbo
Push the current branch to origin:
```sh
git push -u origin <current-branch>
```

## Step 3: Create PR (if needed)

Check if a PR already exists for the current branch:
```sh
gh pr view --repo nicdobler/NukiBlinker
```

If no PR exists, create one:
```sh
gh pr create --title "<title>" --body "<body>" --repo nicdobler/NukiBlinker
```

Skip if PR already exists.

## Step 4: Merge PR

Squash-merge the PR:
```sh
gh pr merge <PR-number> --squash --repo nicdobler/NukiBlinker
```

## Step 5: Switch to main and pull

// turbo
```sh
git checkout main && git pull
```

## Step 6: Clean up branches

Delete local branches that have been merged or whose remote is gone:

// turbo
```powershell
git branch -vv | Select-String ': gone]' | ForEach-Object { ($_ -replace '^\s+' -split '\s+')[0] } | ForEach-Object { git branch -D $_ }
```
