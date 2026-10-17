#!/usr/bin/env bash
# INFRA: wait for data/raw/HI-Small_Trans.csv to finish uploading, verify it, then partition.
# Run on the VM:  nohup bash scripts/partition_when_landed.sh > logs/partition.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/.."
RAW=data/raw/HI-Small_Trans.csv
echo "[$(date -u +%T)] waiting for $RAW"
until [ -s "$RAW" ]; do sleep 15; done
# wait until the size stops changing (scp finished)
prev=-1
while :; do
  cur=$(stat -c %s "$RAW"); [ "$cur" = "$prev" ] && break; prev=$cur; sleep 20
done
echo "[$(date -u +%T)] landed: $(ls -la "$RAW")"
echo "== header"; head -2 "$RAW"
echo "== rows (incl. header)"; wc -l "$RAW"
. .venv/bin/activate
echo "[$(date -u +%T)] partition start"; /usr/bin/time -v python scripts/partition_data.py --raw "$RAW" --out data --seed 42
echo "[$(date -u +%T)] partition done"; du -sh data/banks/* data/global_test.csv data/sample_50k.csv
