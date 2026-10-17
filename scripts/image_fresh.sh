#!/usr/bin/env bash
# INFRA: is image `fedaml` built from the current fedaml/ + Dockerfile?  Uses the image label fedaml.commit
# (set by every INFRA build) and compares the code trees, so a `git pull` right after a build is caught.
#   scripts/image_fresh.sh            exit 0 fresh, 1 stale (prints why)
#   scripts/image_fresh.sh --rebuild  rebuild (labelled with HEAD) if stale, exit 0 on success
set -uo pipefail
cd "${FEDAML_ROOT:-$(dirname "$0")/..}"
head=$(git rev-parse --short HEAD)
lbl=$(docker image inspect fedaml --format '{{index .Config.Labels "fedaml.commit"}}' 2>/dev/null || true)
fresh=1
if [ -z "$lbl" ] || [ "$lbl" = "<no value>" ]; then why="image fedaml missing or unlabelled"; fresh=0
elif ! git cat-file -e "$lbl^{commit}" 2>/dev/null; then why="image label $lbl unknown to this repo"; fresh=0
elif [ -n "$(git diff --name-only "$lbl" HEAD -- fedaml Dockerfile .dockerignore)" ]; then why="fedaml/ or Dockerfile changed between image $lbl and HEAD $head"; fresh=0
elif [ -n "$(git status --porcelain -- fedaml Dockerfile)" ]; then why="uncommitted changes in fedaml/ or Dockerfile on this checkout"; fresh=0
else why="image fedaml built from $lbl; fedaml/ and Dockerfile unchanged up to HEAD $head"; fi
if [ "$fresh" = 1 ]; then echo "fresh: $why"; exit 0; fi
if [ "${1:-}" = "--rebuild" ]; then
  t0=$(date +%s)
  if docker build -q --label fedaml.commit="$head" -t fedaml . >/dev/null 2>&1; then echo "rebuilt: $why -> built from $head in $(( $(date +%s)-t0 ))s"; exit 0
  else echo "STALE and rebuild FAILED: $why"; exit 1; fi
fi
echo "stale: $why"; exit 1
