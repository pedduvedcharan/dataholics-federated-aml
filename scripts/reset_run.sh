#!/usr/bin/env bash
# INFRA: reset a demo run. Clears state/ and run logs, keeps data/ and the INFRA setup logs.
#   scripts/reset_run.sh          clear state/* (except state/examples/) and run logs
#   scripts/reset_run.sh --down   also `docker compose down` first
set -euo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"   # FEDAML_ROOT overrides the project dir (used by smoke tests)
if [ "${1:-}" = "--down" ]; then
  docker compose down --remove-orphans 2>/dev/null || true
fi
scripts/footprint.sh stop >/dev/null 2>&1 || true
mkdir -p state logs/egress
find state -mindepth 1 -maxdepth 1 ! -name examples -exec rm -rf {} +
find logs -mindepth 1 ! -name 'setup_vm.log' ! -name 'docker_build.log' ! -name 'partition.log' -exec rm -rf {} + 2>/dev/null || true
mkdir -p logs/egress state/sar
echo "reset done: state/ and logs/ cleared (data/ untouched)"
ls -la state logs
