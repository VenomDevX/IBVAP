#!/usr/bin/env bash
# Purge leaked strings from the entire git history (audit item H21).
#
# READ docs/SECRET_ROTATION.md FIRST. This rewrites every commit hash.
# Rotate the actual secrets before or after — rotation is what stops a leak
# from being useful; this just tidies the record.
#
# Usage:
#   1. Rotate secrets in the Supabase dashboard (see the doc).
#   2. Edit scripts/secret-replacements.txt — add the real old values.
#   3. From a FRESH MIRROR clone:  git clone --mirror <url> && cd <mirror>
#   4. bash /path/to/scripts/purge_git_secrets.sh
#   5. git push --force --mirror <url>
#   6. Every collaborator re-clones or `git reset --hard origin/<branch>`.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES="$HERE/secret-replacements.txt"

command -v git-filter-repo >/dev/null 2>&1 || {
  echo "git-filter-repo not found. Install it:  pip install git-filter-repo" >&2
  exit 1
}

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1 && ! git rev-parse --is-bare-repository >/dev/null 2>&1; then
  echo "Run this from inside the git repo (ideally a --mirror clone)." >&2
  exit 1
fi

echo "Applying replacements from: $RULES"
grep -vE '^\s*#' "$RULES" | grep -vE '^\s*$' || { echo "No active rules — edit $RULES first." >&2; exit 1; }

git filter-repo --replace-text "$RULES" --force

echo
echo "History rewritten. Next:"
echo "  git push --force --mirror <url>"
echo "  then tell collaborators to re-clone."
