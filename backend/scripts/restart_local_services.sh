#!/bin/zsh

set -euo pipefail

readonly USER_DOMAIN="gui/$(id -u)"
readonly SOURCE_DIR="/Users/kk/KK-Manus/backend/scripts/launchagents"
readonly INSTALL_DIR="${HOME}/Library/LaunchAgents"
readonly LABELS=(com.kkmanus.api com.kkmanus.dramatiq)
readonly PROCESS_PATTERN='(^|/)(python|python3|python3\.11) (api\.py|-m dramatiq .*run_agent_background)'

mkdir -p "${INSTALL_DIR}"

for label in "${LABELS[@]}"; do
  launchctl bootout "${USER_DOMAIN}/${label}" 2>/dev/null || true
done

pkill -TERM -f "${PROCESS_PATTERN}" 2>/dev/null || true

for _ in {1..20}; do
  if ! pgrep -f "${PROCESS_PATTERN}" >/dev/null; then
    break
  fi
  sleep 0.25
done

if pgrep -f "${PROCESS_PATTERN}" >/dev/null; then
  echo "Existing KKManus backend process did not exit; refusing to start duplicates." >&2
  exit 1
fi

for label in "${LABELS[@]}"; do
  cp "${SOURCE_DIR}/${label}.plist" "${INSTALL_DIR}/${label}.plist"
  plutil -lint "${INSTALL_DIR}/${label}.plist" >/dev/null
  launchctl bootstrap "${USER_DOMAIN}" "${INSTALL_DIR}/${label}.plist"
done

echo "KKManus API and Dramatiq restarted with kk-manus/bin/python."
