#!/usr/bin/env bash
# Nightly archive of everything that cannot be rebuilt: results, state, memory,
# secrets. The code and the venv are disposable; these are not.
#
#   deploy/backup.sh [destination]      default: /var/backups/tradingagents
#
# Wire it to cron/systemd-timer at 03:30 Asia/Shanghai.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-/var/backups/tradingagents}"
STAMP="$(date +%Y%m%d-%H%M)"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$DEST"
cd "$ROOT"

tar -czf "$DEST/tradingagents-$STAMP.tar.gz" \
  --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
  "$HOME/.tradingagents" .env 2>/dev/null

# secrets stay owner-only even inside the archive's directory
chmod 600 "$DEST/tradingagents-$STAMP.tar.gz"
find "$DEST" -name 'tradingagents-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "wrote $DEST/tradingagents-$STAMP.tar.gz"
