#!/usr/bin/env bash
# INFRA: go/no-go check before the integration run. Read-only unless --rebuild.
#   scripts/preflight_check.sh            print checks, final line "GO" or "NO-GO: <reasons>", exit 0/1
#   scripts/preflight_check.sh --rebuild  also rebuild image `fedaml` if fedaml/ or Dockerfile changed after it was built
# Never kills processes: anything blocking is reported for its owner (MASTER escalates).
set -uo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"
NOGO=()
ok()   { printf '  OK    %s\n' "$*"; }
bad()  { printf '  NOGO  %s\n' "$*"; NOGO+=("$1"); }
warn() { printf '  WARN  %s\n' "$*"; }
echo "preflight $(date -u +%FT%TZ) on $(hostname) ($(uname -m), $(nproc) cpus)"

# repo + image
git fetch -q origin 2>/dev/null || warn "git fetch failed"
L=$(git rev-parse --short HEAD); R=$(git rev-parse --short origin/main 2>/dev/null || echo "?")
[ "$L" = "$R" ] && ok "repo at origin/main $L" || bad "repo-behind" "repo HEAD $L != origin/main $R (git pull --rebase)"
msg=$(scripts/image_fresh.sh ${1:-} 2>&1); rc=$?
[ $rc -eq 0 ] && ok "$msg" || bad "image-stale" "$msg (run with --rebuild)"

# data
for f in data/banks/bank_{1,2,3,4,5}/train.csv data/banks/bank_{1,2,3,4,5}/test.csv data/global_test.csv data/bank_map.json; do
  [ -s "$f" ] || bad "data" "missing $f"
done
grep -q '"SYNTHETIC": true' data/bank_map.json 2>/dev/null && bad "data-synthetic" "data/bank_map.json is SYNTHETIC" || ok "real partition present (bank_1..5, global_test, bank_map)"

# competing work
p=$(pgrep -d, -x llama-server); [ -z "$p" ] && ok "no host llama-server" || bad "llama-server" "host llama-server running: pid $p ($(ps -o user=,etimes=,rss= -p ${p%%,*} | awk '{printf "%s, up %ds, %d MB", $1,$2,$3/1024}'))"
p=$(pgrep -f -d, 'fedaml\.(coordinator|bank|rogue|baselines|redteam|alerts|sar)' | tr -d ' '); 
[ -z "$p" ] && ok "no host-side fedaml jobs" || bad "host-jobs" "host fedaml processes: $(ps -o pid=,args= -p $p | cut -c1-90 | tr '\n' ';')"
c=$(docker ps --format '{{.Names}}' | grep -vx dashboard | tr '\n' ' ')
[ -z "$c" ] && ok "no containers besides dashboard" || bad "containers" "running containers: $c(run_demo --down would stop compose ones; others need their owner)"
for port in 8000 8050; do
  h=$(sudo -n ss -ltnp 2>/dev/null | grep ":$port " | grep -oE '\("[^"]+",pid=[0-9]+' | head -1)
  if [ -z "$h" ]; then ok "port $port free"
  elif echo "$h" | grep -q docker-proxy; then ok "port $port held by docker-proxy (compose recreates it)"
  else bad "port-$port" "port $port held by non-compose process $h"; fi
done

# resources
load=$(cut -d' ' -f1 /proc/loadavg); avail=$(free -m | awk '/Mem:/{print $7}'); disk=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
awk "BEGIN{exit !($load < 1.5)}" && ok "load1 $load" || bad "load" "load1 $load >= 1.5 on 3 cores"
[ "$avail" -ge 5000 ] && ok "mem available ${avail} MB" || bad "mem" "mem available ${avail} MB < 5000"
[ "$disk" -ge 10 ] && ok "disk free ${disk} GB" || bad "disk" "disk free ${disk} GB < 10"

if [ ${#NOGO[@]} -eq 0 ]; then echo "GO"; exit 0; else echo "NO-GO: ${NOGO[*]}"; exit 1; fi
