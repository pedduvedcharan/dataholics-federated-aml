#!/usr/bin/env bash
# INFRA: one-shot, idempotent VM setup for the LinuxONE box (s390x, Ubuntu 24.04).
# Usage on the VM:  bash ~/fedaml/scripts/setup_vm.sh
# Rules (CLAUDE.md): numpy/scipy/pandas/sklearn come from apt ONLY. pip is for pure-Python packages.
set -euo pipefail

REPO="${REPO:-$HOME/fedaml}"
VENV="$REPO/.venv"
export DEBIAN_FRONTEND=noninteractive

log() { printf '\n[setup_vm %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

log "arch=$(uname -m) cores=$(nproc) mem=$(free -g | awk '/Mem:/{print $2}')G"

log "apt packages"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  python3-venv python3-pip python3-numpy python3-scipy python3-pandas python3-sklearn \
  python3-flask python3-matplotlib python3-requests git docker-compose-v2 strace

log "venv (system site packages) at $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv --system-site-packages "$VENV"
fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
python -m pip install -q --upgrade pip >/dev/null 2>&1 || true

# Never let pip compile numpy/scipy/pandas/sklearn on s390x: refuse non-wheel installs of them.
PIP_FLAGS=(--only-binary numpy,scipy,pandas,scikit-learn)

PIP_OK=()
PIP_FAIL=()
try_pip() {
  local pkg="$1"
  log "pip install $pkg"
  if timeout 600 pip install -q "${PIP_FLAGS[@]}" "$pkg"; then
    PIP_OK+=("$pkg")
  else
    PIP_FAIL+=("$pkg")
    log "WARN: pip install $pkg failed (continuing)"
  fi
}
try_pip phe                               # required (Paillier, pure Python)
try_pip dilithium-py                      # stretch (ML-DSA signing, pure Python)
try_pip adversarial-robustness-toolbox    # optional (REDTEAM has a fallback)

log "data/state/logs layout"
mkdir -p "$REPO/data/raw" "$REPO/data/banks" "$REPO/state" "$REPO/logs/egress"

log "verify imports"
python - <<'PY'
import importlib, platform
mods = ["numpy", "scipy", "pandas", "sklearn", "flask", "matplotlib", "requests", "phe"]
opt = ["dilithium_py", "art"]
print("python", platform.python_version(), platform.machine())
for m in mods:
    mod = importlib.import_module(m)
    print(f"  OK  {m:12s} {getattr(mod, '__version__', '')}")
for m in opt:
    try:
        mod = importlib.import_module(m)
        print(f"  OK  {m:12s} {getattr(mod, '__version__', '')} (optional)")
    except Exception as e:  # noqa: BLE001
        print(f"  --  {m:12s} not available (optional): {type(e).__name__}")
PY

log "docker"
docker --version
docker compose version || log "WARN: docker compose plugin missing"

log "SUMMARY pip ok:   ${PIP_OK[*]:-none}"
log "SUMMARY pip fail: ${PIP_FAIL[*]:-none}"
log "done. Activate with:  . $VENV/bin/activate"
