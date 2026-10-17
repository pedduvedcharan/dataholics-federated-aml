#!/usr/bin/env bash
# INFRA: text "screenshots" for judging criterion 3 (containers, security, compute on LinuxONE).
#   scripts/capture_screens.sh            capture now
#   scripts/capture_screens.sh --wait     wait (up to WAIT_S, default 1800 s) until >= 2 bank containers run, then capture
# Writes submission/screenshots/01_vm_facts.txt (uname -a, lscpu, free, df, docker version, images)
#    and submission/screenshots/02_docker_ps.txt (+ a timestamped copy 02_docker_ps_<UTC>.txt) with
#    docker ps, docker stats --no-stream, and the coordinator's live /status round line.
set -uo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"
OUT=submission/screenshots; mkdir -p "$OUT"
if [ "${1:-}" = "--wait" ]; then
  t0=$(date +%s); W="${WAIT_S:-1800}"
  echo "waiting up to ${W}s for bank containers..."
  until [ "$(docker ps --format '{{.Names}}' | grep -cE '^bank[1-4]$')" -ge 2 ]; do
    [ $(( $(date +%s) - t0 )) -gt "$W" ] && { echo "no banks within ${W}s; capturing anyway"; break; }
    sleep 1
  done
  sleep 4   # let the banks get into local training
fi
{ echo "# captured $(date -u +%FT%TZ) on $(hostname)"
  echo "\$ uname -a"; uname -a; echo
  echo "\$ lscpu | head -20"; lscpu | head -20; echo
  echo "\$ free -h"; free -h; echo
  echo "\$ df -h /"; df -h /; echo
  echo "\$ docker version --format '{{.Server.Os}}/{{.Server.Arch}} {{.Server.Version}}'"
  docker version --format '{{.Server.Os}}/{{.Server.Arch}} {{.Server.Version}}'; echo
  echo "\$ docker images fedaml"; docker images fedaml; } > "$OUT/01_vm_facts.txt" 2>&1
TS=$(date -u +%Y%m%dT%H%M%SZ)
{ echo "# captured $(date -u +%FT%TZ) ($(uname -m), $(nproc) cpus)"
  echo "\$ docker ps"; docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"; echo
  echo "\$ docker stats --no-stream"; docker stats --no-stream; echo
  echo "\$ curl -s 127.0.0.1:8000/status  (round progress)"
  curl -s -m 3 127.0.0.1:8000/status 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print({k: d.get(k) for k in ('current_round','total_rounds','banks_expected','waiting_for')}, 'dp', {k: d['dp'].get(k) for k in ('enabled','mode','sigma','clip_norm')})" 2>/dev/null || echo "(coordinator not reachable)"
} > "$OUT/02_docker_ps_$TS.txt" 2>&1
cp "$OUT/02_docker_ps_$TS.txt" "$OUT/02_docker_ps.txt"
echo "wrote $OUT/01_vm_facts.txt and $OUT/02_docker_ps_$TS.txt (banks in capture: $(grep -cE '^bank[1-4] ' "$OUT/02_docker_ps_$TS.txt"))"
