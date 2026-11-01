#!/usr/bin/env bash
# Sync the downstream `main` onto an official release tag.
#
# Rules this script enforces (docs/UPSTREAM_SYNC.md §2):
#   * production follows a release TAG, never upstream/main;
#   * the sync happens on its own branch, from an immutable backup tag;
#   * the advance only lands if the full suite passes;
#   * the upstream base is recorded in a tracked file;
#   * nothing is pushed automatically — a rebased main needs force-with-lease,
#     and that is a human decision made once nobody else is pushing.
#
# Usage: scripts/sync_upstream.sh v0.7.2 [--version 0.2.0]

set -euo pipefail

TAG="${1:?usage: scripts/sync_upstream.sh <upstream-tag> [--version X.Y.Z]}"
shift || true
DOWNSTREAM_VERSION=""
if [[ "${1:-}" == "--version" ]]; then
  DOWNSTREAM_VERSION="${2:?--version needs a value}"
fi

cd "$(dirname "$0")/.."

if [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree is dirty; commit or stash before syncing" >&2
  exit 1
fi
if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "sync from main (current: $(git rev-parse --abbrev-ref HEAD))" >&2
  exit 1
fi

git fetch upstream --tags --quiet
if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "upstream tag ${TAG} not found after fetch" >&2
  exit 1
fi

BASE="$(git rev-parse --short "${TAG}^{commit}")"
STAMP="$(date +%Y%m%d-%H%M)"
BACKUP="backup/pre-sync-${TAG}-${STAMP}"
SYNC="sync/${TAG}"

echo "==> upstream ${TAG} = ${BASE}"
git tag -a "$BACKUP" -m "immutable backup before syncing ${TAG}" main
echo "==> backup tag ${BACKUP}"

git switch -q -c "$SYNC" main
if ! git rebase "${TAG}"; then
  cat >&2 <<EOF

Rebase stopped. Resolve on ${SYNC}, then:
  git add <files> && git rebase --continue
or abort with:
  git rebase --abort && git switch main && git branch -D ${SYNC}

Backup stays at ${BACKUP}. Nothing was pushed.
EOF
  exit 1
fi

echo "==> running the full suite"
if ! uv run pytest -q; then
  cat >&2 <<EOF

Tests failed on ${SYNC}. Production was NOT advanced.
Backup: ${BACKUP}. Investigate, fix here, and re-run scripts/sync_upstream.sh
after aborting this branch.
EOF
  exit 1
fi
uv run ruff check .

printf '# Upstream base\n\n- tag: %s\n- commit: %s\n- synced: %s\n- downstream branch: %s\n' \
  "$TAG" "$BASE" "$(date +%Y-%m-%d)" "$SYNC" > docs/UPSTREAM_BASE.md
git add docs/UPSTREAM_BASE.md
git commit -q -m "chore(sync): advance upstream base to ${TAG} (${BASE})"

if [[ -n "$DOWNSTREAM_VERSION" ]]; then
  git tag -a "downstream-v${DOWNSTREAM_VERSION}" -m "downstream release on upstream ${TAG}"
  echo "==> tagged downstream-v${DOWNSTREAM_VERSION}"
fi

git switch -q main
git merge --ff-only "$SYNC"
echo
cat <<EOF
Merged ${SYNC} into main. Still local — publishing a rebased main needs:
  git push --force-with-lease origin main
Only after confirming nobody else is pushing, and after:
  git push origin ${BACKUP} ${TAG} ${DOWNSTREAM_VERSION:+downstream-v${DOWNSTREAM_VERSION}}
EOF
