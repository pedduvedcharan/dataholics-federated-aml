#!/usr/bin/env bash
# INFRA: one-command demo rehearsal for MASTER.
#
#   scripts/run_demo.sh                 reset -> DP-off run -> DP-on run (demo) -> tryleak -> attacker, alerts, genai -> footprint
#   scripts/run_demo.sh --skip-off      only the DP-on run (attacker is skipped unless global_final_dpoff.json already exists)
#   scripts/run_demo.sh --no-reset      keep existing state/ and logs/
#   scripts/run_demo.sh --no-tools      stop after training (dashboard stays up)
#   scripts/run_demo.sh --no-rogue      4 honest banks only: BANKS=1,2,3,4, rogue service not started (MASTER 16:20 fallback:
#                                       the rogue scene then comes from archived DP-off files; status_rogue_on.json is NOT written)
#
# Knobs are the compose env vars: ROUNDS EPOCHS SIGMA DP_MODE CLIP TAU SEED BANKS EVAL_BANKS TRAINER ROGUE_ATTACK ROGUE_FACTOR ALERT_ID SAR_ENGINE (default template) LLM_MODEL_FILE.
# TAG is set per phase (dpoff, dpon) so the coordinator writes state/global_final_<tag>.json itself.
# WAIT_MAX (default 1800 s) bounds each training phase. COMPOSE_EXTRA adds compose flags (e.g. "-f smoke/override.yml").
# Both runs keep DEFENSE on so the DP off/on comparison differs in DP only (REDTEAM's request).
# Writes: state/global_final_dpoff.json, state/global_final_dpon.json (+ status_dpoff/dpon.json, status_rogue_on.json),
#         state/redteam.json, state/alerts.json, state/sar/*.md, state/footprint.json, logs/footprint.log,
#         submission/screenshots/02_docker_ps.txt (text capture of `docker ps` + `docker stats` during the run).
set -uo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"
DC="docker compose ${COMPOSE_EXTRA:-}"
export SAR_ENGINE="${SAR_ENGINE:-template}"   # compose defaults genai to llm; the integration run uses template (MASTER)
WAIT_MAX="${WAIT_MAX:-1800}"
DO_OFF=1; DO_RESET=1; DO_TOOLS=1; DO_ROGUE=1
for a in "$@"; do
  case "$a" in
    --skip-off) DO_OFF=0 ;; --no-reset) DO_RESET=0 ;; --no-tools) DO_TOOLS=0 ;; --no-rogue) DO_ROGUE=0 ;;
    *) echo "unknown flag $a"; exit 2 ;;
  esac
done
TRAIN_SVCS="coordinator bank1 bank2 bank3 bank4 rogue"
if [ "$DO_ROGUE" = 0 ]; then TRAIN_SVCS="coordinator bank1 bank2 bank3 bank4"; export BANKS="${BANKS:-1,2,3,4}"; fi
log() { printf '\n[run_demo %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "FAIL: $*"; $DC logs --tail 30 coordinator 2>/dev/null | tail -30; exit 1; }

# ---------------------------------------------------------------- preflight
log "preflight in $(pwd)"
[ -f data/banks/bank_1/train.csv ] || die "data/banks/bank_1/train.csv missing (run scripts/partition_data.py)"
if grep -q '"SYNTHETIC": true' data/bank_map.json 2>/dev/null; then
  log "WARNING: data/bank_map.json is SYNTHETIC. This is a dry run; no number from it goes on a slide."
fi
docker image inspect fedaml >/dev/null 2>&1 || die "image 'fedaml' missing: docker build -t fedaml ."
for port in ${DEMO_PORTS:-8000 8050}; do   # host ports compose publishes
  if ss -ltn 2>/dev/null | grep -q ":$port "; then
    holder=$(sudo ss -ltnp 2>/dev/null | grep ":$port " | grep -oE 'pid=[0-9]+' | head -1)
    if ! docker ps --format '{{.Ports}}' | grep -q ":$port->"; then
      die "host port $port is taken by a non-compose process ($holder). Stop it first (e.g. kill ${holder#pid=})."
    fi
  fi
done

# ---------------------------------------------------------------- reset + footprint
if [ "$DO_RESET" = 1 ]; then
  scripts/reset_run.sh --down
  # Carry over outputs this run does NOT regenerate (rogue scene from FEDERATION's DP-off runs, MODELS baselines,
  # GENAI LLM benchmarks), from the newest archive that has each file. Override with RESTORE_GLOBS.
  RESTORE_GLOBS="${RESTORE_GLOBS:-status_rogue_*.json global_final_rogue_*.json baselines.json llm_*.json}"
  for g in $RESTORE_GLOBS; do
    for f in $(ls -1t archive/*/state/$g 2>/dev/null); do
      b=$(basename "$f"); [ -e "state/$b" ] || { cp -p "$f" "state/$b" && echo "  restored state/$b <- $f"; }
    done
  done
fi
mkdir -p state logs/egress submission/screenshots
scripts/footprint.sh start
T_START=$(date +%s)

wait_final() {  # $1 = epoch the phase started
  local since="$1" t0; t0=$(date +%s)
  while :; do
    if [ -f state/global_final.json ] && [ "$(stat -c %Y state/global_final.json)" -ge "$since" ]; then return 0; fi
    local st; st=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' coordinator 2>/dev/null || echo "missing 0")
    case "$st" in exited*) die "coordinator exited before writing global_final.json ($st)";; esac
    for b in bank1 bank2 bank3 bank4 rogue; do
      s=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$b" 2>/dev/null || true)
      case "$s" in "exited 0"|"") ;; exited*) log "note: $b $s (coordinator closes the round on timeout)";; esac
    done
    [ $(( $(date +%s) - t0 )) -gt "$WAIT_MAX" ] && die "timed out after ${WAIT_MAX}s waiting for the final round"
    sleep 5
  done
}

run_phase() {  # $1 = tag (dpoff|dpon), $2 = DP value
  local tag="$1" dp="$2" t; t=$(date +%s)
  local coord_cmd; coord_cmd=$(DP="$dp" TAG="$tag" $DC config --format json 2>/dev/null | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)['services']['coordinator']['command']))" 2>/dev/null)
  log "phase $tag: coordinator = ${coord_cmd:-<could not render>}"
  log "phase $tag: DP=$dp DP_MODE=${DP_MODE:-<compose default>} SIGMA=${SIGMA:-<compose default>} MU=${MU:-<compose default>} DEFENSE=on ROUNDS=${ROUNDS:-10} BANKS=${BANKS:-1,2,3,4,5} EVAL_BANKS=${EVAL_BANKS:-2,3,4} rogue=$([ "$DO_ROGUE" = 1 ] && echo on || echo off)"
  $DC rm -fs $TRAIN_SVCS rogue >/dev/null 2>&1 || true
  DP="$dp" DEFENSE=on TAG="$tag" $DC up -d $TRAIN_SVCS dashboard || die "docker compose up failed"
  local cap_pid=""
  if [ "$tag" = "dpon" ]; then WAIT_S=60 scripts/capture_screens.sh --wait > logs/capture_screens.log 2>&1 & cap_pid=$!; fi
  sleep 3
  wait_final "$t"
  [ -n "$cap_pid" ] && wait "$cap_pid" 2>/dev/null
  log "phase $tag finished in $(( $(date +%s) - t ))s"
  # compose passes TAG to the coordinator (--tag) which writes these itself; copy only if it did not
  [ -f "state/global_final_${tag}.json" ] || cp state/global_final.json "state/global_final_${tag}.json"
  [ -f "state/status_${tag}.json" ] || cp state/status.json "state/status_${tag}.json"
  python3 - "$tag" <<'PY'
import json, sys
d = json.load(open("state/status.json"))
print(f"  rounds={d.get('round')} seconds_per_round={d.get('seconds_per_round')} total_runtime_s={d.get('total_runtime_s')}")
for r in d.get("rounds", [])[-1:]:
    print(f"  last round: accepted={r.get('accepted')} excluded={[e.get('bank_id') for e in r.get('excluded', [])]} global_auc={r.get('global_auc')} global_ap={r.get('global_ap')}")
print(f"  dp={d.get('dp')}")
PY
}

# ---------------------------------------------------------------- training runs
[ "$DO_OFF" = 1 ] && run_phase dpoff off
run_phase dpon on
[ "$DO_ROGUE" = 1 ] && cp state/status.json state/status_rogue_on.json   # defense on: rogue exclusions visible to the dashboard


if [ "$DO_TOOLS" = 1 ]; then
  log "tryleak: 5 raw rows through egress.send must be BLOCKED (coordinator is still lingering)"
  $DC run --rm tryleak && log "tryleak: blocked as expected" || log "tryleak exit $? (0 = blocked)"
  if [ -f state/global_final_dpoff.json ] && [ -f state/global_final_dpon.json ]; then
    log "attacker (membership inference, DP off vs on)"
    $DC run --rm attacker || log "attacker failed (exit $?)"
  else
    log "attacker skipped: need both state/global_final_dpoff.json and state/global_final_dpon.json"
  fi
  log "alerts (top-20 flagged chains from the DP-on model)"
  $DC run --rm alerts || log "alerts failed (exit $?)"
  log "genai (SAR for ${ALERT_ID:-A01}, engine ${SAR_ENGINE:-template})"
  if [ "${SAR_ENGINE:-template}" = "llm" ]; then   # genai no longer depends_on llm (MASTER): start/stop it explicitly
    log "starting llm (LLM_MODEL_FILE=${LLM_MODEL_FILE:-default})"; $DC up -d --wait llm || log "llm failed to start; sar.py falls back to template"
  fi
  $DC run --rm genai || log "genai failed (exit $?)"
  [ "${SAR_ENGINE:-template}" = "llm" ] && { $DC stop llm >/dev/null 2>&1 || true; }
fi

$DC stop $TRAIN_SVCS rogue >/dev/null 2>&1 || true
log "footprint"
scripts/footprint.sh stop
if [ -n "$(find state logs -not -user "$(id -un)" -print -quit 2>/dev/null)" ]; then   # containers write as root
  sudo -n chown -R "$(id -u):$(id -g)" state logs 2>/dev/null && sudo -n chmod -R u+rwX,go+rX state logs 2>/dev/null \
    && log "state/ and logs/ handed back to $(id -un)" || log "WARN: could not chown state/ logs/ (sudo)"
fi
log "done in $(( $(date +%s) - T_START ))s. state/:"; ls -la state | grep -v '^total'
log "dashboard still up: ssh -L 8050:localhost:8050 dataholics  ->  http://localhost:8050"
