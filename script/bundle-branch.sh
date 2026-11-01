#!/usr/bin/env bash
#
# bundle-branch.sh [branch] [base]
#
# Packages the commits unique to a branch into a git bundle, encodes it as
# Base64 and splits it into chunks of CHUNK_LINES lines for transport.
#
#   1. Creates <safe>.bundle with only the branch commits vs <base>
#      (uses <base>..<branch> to keep the file small — thin bundle).
#   2. Verifies it with `git bundle verify`.
#   3. Base64-encodes it (76 cols) and splits into
#      <safe>.bundle.b64.001, .002, ... of CHUNK_LINES lines each.
#   4. Prints reconstruction + import/push/PR instructions.
#
# Args:
#   branch   Branch to bundle. Default: current branch.
#   base     Base ref the commits are computed against. Default: main.
#
# Env:
#   CHUNK_LINES  Lines per Base64 chunk. Default: 1000.
#   OUTPUT_DIR   Output directory. Default: repository root.
#
# Example:
#   script/bundle-branch.sh
#   script/bundle-branch.sh feat/99and100
#   CHUNK_LINES=500 script/bundle-branch.sh feat/99and100 main

set -euo pipefail

Branch="${1:-}"
Base="${2:-main}"
ChunkLines="${CHUNK_LINES:-1000}"
OutputDir="${OUTPUT_DIR:-}"

# ── Resolve branch ────────────────────────────────────────────────────────────
if [ -z "$Branch" ]; then
    Branch="$(git rev-parse --abbrev-ref HEAD)" || {
        echo "ERROR: could not resolve current branch. Run inside the repository." >&2
        exit 1
    }
fi

if [ "$Branch" = "$Base" ]; then
    echo "ERROR: branch '$Branch' is the same as base '$Base'. Switch to a feature branch." >&2
    exit 1
fi

# ── Resolve output dir ────────────────────────────────────────────────────────
if [ -z "$OutputDir" ]; then
    OutputDir="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
fi

# File name: '/' and '\' -> '-' to avoid subdirectories
SafeName="${Branch//\//-}"
SafeName="${SafeName//\\/-}"
BundlePath="$OutputDir/$SafeName.bundle"
B64Path="$BundlePath.b64"

# ── Exclusive commits ─────────────────────────────────────────────────────────
echo ""
echo "[*] Branch: $Branch"
echo "[*] Base:   $Base"

commits="$(git log --oneline "$Base..$Branch" 2>/dev/null || true)"
if [ -z "$commits" ]; then
    echo "[!] No exclusive commits on '$Branch' vs '$Base'."
    exit 0
fi

echo ""
echo "[i] Commits included in the bundle:"
echo "$commits" | sed 's/^/   /'

# ── Create bundle ─────────────────────────────────────────────────────────────
echo ""
echo "[*] Creating bundle: $BundlePath"
git bundle create "$BundlePath" "$Base..$Branch"
bundleSize="$(du -k "$BundlePath" | cut -f1)"
echo "[OK] Bundle created (${bundleSize} KB)"

# ── Verify bundle ─────────────────────────────────────────────────────────────
echo ""
echo "[*] Verifying bundle..."
git bundle verify "$BundlePath" 2>&1 | sed 's/^/    /'
echo "[OK] Bundle verified"

# ── Base64 + split ────────────────────────────────────────────────────────────
echo ""
echo "[*] Encoding to Base64 (76 cols) and splitting into $ChunkLines-line chunks..."
b64tmp="$(mktemp)"
trap 'rm -f "$b64tmp"' EXIT
base64 < "$BundlePath" | tr -d '\n' | fold -w 76 > "$b64tmp"

# Portable chunking (no GNU-only flags): awk writes .001, .002, ... files
rm -f "$B64Path".[0-9][0-9][0-9]
awk -v lines="$ChunkLines" -v prefix="$B64Path." \
    '{ print > sprintf("%s%03d", prefix, int((NR - 1) / lines) + 1) }' "$b64tmp"

chunks=0
for f in "$B64Path".[0-9][0-9][0-9]; do
    chunks=$((chunks + 1))
    chunkKB="$(du -k "$f" | cut -f1)"
    echo "   Chunk -> $(basename "$f") (${chunkKB} KB)"
done
echo "[OK] $chunks chunk(s) generated in $OutputDir"

baseShort="$(git rev-parse --short "$Base")"

# ── Reconstruction instructions ───────────────────────────────────────────────
cat <<EOF

----------------------------------------------------------------
 NOTE: this is a THIN bundle — the destination repo must already
 contain the base ref '$Base' ($baseShort) for import to work.

 Rebuild the bundle on the destination machine:

   bash:
     cat $SafeName.bundle.b64.* | tr -d '\\n' | base64 -d > $SafeName.bundle
     # macOS: use 'base64 -D' instead of 'base64 -d'

   PowerShell:
     Get-Content $SafeName.bundle.b64.* | Set-Content joined.b64 -Encoding ascii
     \$b64 = Get-Content joined.b64 -Raw
     [IO.File]::WriteAllBytes('$SafeName.bundle', [Convert]::FromBase64String(\$b64.Trim()))

 Then verify, import, push and open the PR:

     git bundle verify $SafeName.bundle
     git fetch $SafeName.bundle $Branch:$Branch
     git checkout $Branch
     git push -u origin $Branch
     gh pr create
----------------------------------------------------------------

EOF
