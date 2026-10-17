#!/usr/bin/env bash
# INFRA: measure the container footprint of a full compose run on the LinuxONE VM.
#   scripts/footprint.sh start    sample `docker stats` every 5 s into logs/footprint.log (background)
#   scripts/footprint.sh stop     stop sampling and write state/footprint.json
#   scripts/footprint.sh report   (re)write state/footprint.json from the existing log
# Round timing comes from the mtimes of state/global_round_<r>.json (coordinator writes one per round).
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=logs/footprint.log
PIDFILE=state/.footprint.pid
INTERVAL="${FOOTPRINT_INTERVAL:-5}"
mkdir -p logs state

case "${1:-}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "already sampling (pid $(cat "$PIDFILE"))"; exit 0
    fi
    : > "$LOG"
    echo "# start $(date +%s) $(date -u +%FT%TZ) arch=$(uname -m) cpus=$(nproc)" >> "$LOG"
    nohup bash -c "while true; do
        ts=\$(date +%s)
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' 2>/dev/null | sed \"s/^/\$ts /\"
        sleep $INTERVAL
      done >> '$LOG' 2>/dev/null" >/dev/null 2>&1 &
    echo $! > "$PIDFILE"
    echo "sampling every ${INTERVAL}s -> $LOG (pid $!)"
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      pkill -f "docker stats --no-stream" 2>/dev/null || true
      rm -f "$PIDFILE"
    fi
    echo "# stop $(date +%s) $(date -u +%FT%TZ)" >> "$LOG"
    exec "$0" report
    ;;
  report)
    python3 - "$LOG" <<'PY'
import glob, json, os, re, sys, time, platform

log = sys.argv[1]
peak, start, stop, samples = {}, None, None, 0
unit = {"B": 1 / 2**20, "KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0, "kB": 1e3 / 2**20, "MB": 1e6 / 2**20, "GB": 1e9 / 2**20}
for line in open(log):
    if line.startswith("# start"):
        start = int(line.split()[2]); continue
    if line.startswith("# stop"):
        stop = int(line.split()[2]); continue
    m = re.match(r"(\d+) (\S+) ([\d.]+)(\w+) /", line)
    if not m:
        continue
    samples += 1
    mb = float(m.group(3)) * unit.get(m.group(4), 1.0)
    name = m.group(2)
    peak[name] = max(peak.get(name, 0.0), mb)

rounds = sorted(glob.glob("state/global_round_*.json"), key=lambda p: int(re.search(r"(\d+)\.json$", p).group(1)))
mtimes = [os.path.getmtime(p) for p in rounds]
gaps = [b - a for a, b in zip(mtimes, mtimes[1:])]
seconds_per_round = round(sum(gaps) / len(gaps), 1) if gaps else None
if stop is None:
    stop = int(time.time())
total = (stop - start) if start else (round(mtimes[-1] - mtimes[0]) if len(mtimes) > 1 else None)

out = {
    "per_container_peak_rss_mb": {k: round(v, 1) for k, v in sorted(peak.items())},
    "total_peak_rss_mb_sum": round(sum(peak.values()), 1),
    "seconds_per_round": seconds_per_round,
    "rounds_observed": len(rounds),
    "total_runtime_s": total,
    "cpu_count": os.cpu_count(),
    "arch": platform.machine(),
    "samples": samples,
    "sample_interval_s": int(os.environ.get("FOOTPRINT_INTERVAL", "5")),
    "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sources": {"memory": log, "rounds": "mtime of state/global_round_<r>.json"},
}
os.makedirs("state", exist_ok=True)
tmp = "state/footprint.json.tmp"
json.dump(out, open(tmp, "w"), indent=2)
os.replace(tmp, "state/footprint.json")
print(json.dumps(out, indent=2))
PY
    ;;
  *)
    echo "usage: $0 start|stop|report"; exit 2 ;;
esac
