#!/bin/sh
# Download a small instruct GGUF and convert it to big-endian for IBM Z. Runs inside the fedaml-llm
# image (or on the VM with llama.cpp's gguf-py on PYTHONPATH). Idempotent. GENAI owns this file.
#   MODEL_REPO   HF repo with GGUFs            (default Qwen/Qwen2.5-0.5B-Instruct-GGUF)
#   MODEL_FILE   little-endian file in repo    (default qwen2.5-0.5b-instruct-q8_0.gguf)
#   MODELS_DIR   output directory              (default /models)
set -eu
MODEL_REPO="${MODEL_REPO:-Qwen/Qwen2.5-0.5B-Instruct-GGUF}"
MODEL_FILE="${MODEL_FILE:-qwen2.5-0.5b-instruct-q8_0.gguf}"
MODELS_DIR="${MODELS_DIR:-/models}"
GGUF_PY="${GGUF_PY:-/app/gguf-py}"
BE_FILE="${MODELS_DIR}/$(basename "$MODEL_FILE" .gguf)-be.gguf"
mkdir -p "$MODELS_DIR"
if [ -s "$BE_FILE" ]; then echo "already present: $BE_FILE"; exit 0; fi
t0=$(date +%s)
echo "downloading $MODEL_REPO/$MODEL_FILE"
curl -L --retry 3 -o "$MODELS_DIR/$MODEL_FILE" "https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE"
t1=$(date +%s)
echo "converting to big-endian -> $BE_FILE"
cp "$MODELS_DIR/$MODEL_FILE" "$BE_FILE.tmp"
echo YES | PYTHONPATH="$GGUF_PY" python3 "$GGUF_PY/gguf/scripts/gguf_convert_endian.py" "$BE_FILE.tmp" big
mv "$BE_FILE.tmp" "$BE_FILE"
rm -f "$MODELS_DIR/$MODEL_FILE"
t2=$(date +%s)
PYTHONPATH="$GGUF_PY" python3 "$GGUF_PY/gguf/scripts/gguf_dump.py" --no-tensors "$BE_FILE" | grep -iE "endian|architecture|size_label" || true
echo "download_s=$((t1-t0)) convert_s=$((t2-t1)) file=$BE_FILE"
