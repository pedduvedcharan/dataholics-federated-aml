#!/usr/bin/env bash
# INFRA: reset a demo run. ARCHIVES (never deletes) state/ and run logs, keeps data/ and the INFRA setup logs.
#   scripts/reset_run.sh          move state/* (except examples/) and run logs to archive/<UTC timestamp>/
#   scripts/reset_run.sh --down   also `docker compose down` first
# Other agents' outputs (baselines.json, alerts.json, redteam*.json, sweep models) survive in the archive:
#   cp archive/<ts>/state/baselines.json state/
set -euo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"   # FEDAML_ROOT overrides the project dir (used by smoke tests)
if [ "${1:-}" = "--down" ]; then
  docker compose ${COMPOSE_EXTRA:-} down --remove-orphans 2>/dev/null || true
fi
[ -f state/.footprint.pid ] && { scripts/footprint.sh stop >/dev/null 2>&1 || true; }   # only if sampling is live
TS=$(date -u +%Y%m%dT%H%M%SZ)
DEST="archive/$TS"
mkdir -p "$DEST/state" "$DEST/logs" state logs/egress
SUDO=""; [ -n "$(find state logs -user root -print -quit 2>/dev/null)" ] && SUDO="sudo"   # containers write as root
find state -mindepth 1 -maxdepth 1 ! -name examples -exec $SUDO mv {} "$DEST/state/" \; 2>/dev/null || true
find logs -mindepth 1 -maxdepth 1 ! -name 'setup_vm.log' ! -name 'docker_build.log' ! -name 'partition.log' \
  ! -name 'apt_buildtools.log' -exec $SUDO mv {} "$DEST/logs/" \; 2>/dev/null || true
[ -n "$SUDO" ] && sudo chown -R "$(id -u):$(id -g)" "$DEST" 2>/dev/null || true
mkdir -p logs/egress state/sar
echo "reset done: previous state/ and logs/ archived to $DEST (data/ untouched)"
ls "$DEST/state" | head -40
