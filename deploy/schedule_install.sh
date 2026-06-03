#!/usr/bin/env bash
# Install/uninstall the SECFEDCLAW v0.2 daily run.
#   macOS:  ./deploy/schedule_install.sh install     (launchd, weekdays 16:35 local)
#           ./deploy/schedule_install.sh uninstall
#           ./deploy/schedule_install.sh status
#   Linux:  see deploy/secfedclaw.cron (crontab).
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"          # repo root (parent of deploy/)
PY="$(command -v python3)"
LABEL="com.alphaomega.secfedclaw.daily"
PLIST_SRC="$DIR/deploy/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
ACTION="${1:-install}"

case "$(uname -s)" in
  Darwin) ;;
  *) echo "Non-macOS host. Use deploy/secfedclaw.cron with crontab instead."; exit 0 ;;
esac

case "$ACTION" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
    sed -e "s#__PYTHON__#$PY#g" -e "s#__DIR__#$DIR#g" "$PLIST_SRC" > "$PLIST_DST"
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    launchctl load "$PLIST_DST"
    echo "Installed $LABEL -> $PLIST_DST"
    echo "Runs weekdays 16:35 local. Logs: $DIR/logs/  Summary: $DIR/out/daily_run_summary.json"
    echo "Run once now: launchctl start $LABEL"
    ;;
  uninstall)
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm -f "$PLIST_DST"
    echo "Uninstalled $LABEL"
    ;;
  status)
    launchctl list | grep "$LABEL" || echo "$LABEL not loaded"
    ;;
  *) echo "usage: $0 {install|uninstall|status}"; exit 2 ;;
esac
