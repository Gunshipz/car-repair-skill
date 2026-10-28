#!/usr/bin/env bash
# Push the garage stack to a server from the PC (Git Bash). No rsync needed: tar over ssh.
# Usage: server/deploy.sh --host IP --user USER [--key ~/.ssh/id_ed25519] [--dry-run]   (key path without spaces)
# Does NOT start compose or enable the timer: the first runs are deliberate (see README.md).
set -euo pipefail
HOST= USER_= DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST=$2; shift 2 ;;
    --user) USER_=$2; shift 2 ;;
    --key) KEY=$2; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
[ -n "$HOST" ] && [ -n "$USER_" ] || { echo "usage: deploy.sh --host IP --user USER [--key FILE] [--dry-run]" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(dirname "$HERE")
SSH=(ssh ${KEY:+-i "$KEY"} -o BatchMode=yes -o ConnectTimeout=10 "$USER_@$HOST")
G=/home/$USER_/garage
run() { if [ "$DRY" = 1 ]; then printf 'DRY: %s\n' "$*"; else "$@"; fi; }

run "${SSH[@]}" "mkdir -p $G/mygarage-data $G/yard $G/carkit"
# server files (never overwrite the live .env or yard state)
FILES=$({ cd "$HERE" && ls compose.yml garage-yard.service garage-yard.timer *.md 2>/dev/null || true; } | tr '
' ' ')
run bash -c "tar -C '$HERE' -cf - $FILES | ${SSH[*]} 'tar -C $G -xf -'"
run bash -c "${SSH[*]} 'test -f $G/yard/watchlist.json' || tar -C '$HERE' -cf - watchlist.json | ${SSH[*]} 'tar -C $G/yard -xf -'"
# carkit and its modules, without tests or fixtures
run bash -c "tar -C '$SKILL/scripts' --exclude='test_*' --exclude=fixtures --exclude=__pycache__ -cf - . | ${SSH[*]} 'tar -C $G/carkit -xf -'"
# units are written with USER placeholders; fill in the target's user and home
run "${SSH[@]}" "sed -i 's#/home/USER/#/home/$USER_/#g; s#^User=USER#User=$USER_#' $G/garage-yard.service && sudo install -m 644 $G/garage-yard.service $G/garage-yard.timer /etc/systemd/system/ && sudo systemctl daemon-reload"
echo "deployed to $USER_@$HOST:$G (compose and timer left as they are)"
