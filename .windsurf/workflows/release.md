---
description: Create a new release — tag, changelog, Docker build
---

# Release Workflow

Use this workflow when you're ready to tag a new release from `main`.

## Prerequisites

- All changes merged to `main`
- CHANGELOG.md updated with changes in `[Unreleased]` section
- `make test` and `make lint` pass

## Steps

### 1. Ensure you're on main with latest changes

```bash
git checkout main
git pull origin main
```

### 2. Verify tests and lint pass

// turbo
```sh
make test
```

// turbo
```sh
make lint
```

### 3. Verify CHANGELOG.md is updated

Check that `[Unreleased]` section contains all changes being released.

### 4. Choose version number

Follow semantic versioning (MAJOR.MINOR.PATCH).

### 5. Update CHANGELOG.md

Move `[Unreleased]` contents to a new version section:

**Before:**
```markdown
## [Unreleased]

### Added
- New feature X
```

**After:**
```markdown
## [Unreleased]

## [X.Y.Z] - YYYY-MM-DD

### Added
- New feature X
```

### 6. Commit, tag, and push

```bash
git add CHANGELOG.md
git commit -m "release: vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

### 7. Build Docker image

```sh
make build
```

### 8. (Optional) Create GitHub release

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG.md for details"
```
