# llama.cpp built from source for IBM Z (s390x, big-endian), CPU only. Serves a big-endian GGUF
# over HTTP (OpenAI-compatible) on :8080 for the `genai` service. GENAI owns this file.
#
#   docker build -f fedaml/llm/Dockerfile -t fedaml-llm .
#   docker run --rm -v ./models:/models fedaml-llm /app/fetch_model.sh        # one-off: download + big-endian convert
#   docker run --rm -p 127.0.0.1:8080:8080 -v ./models:/models fedaml-llm     # serve
#
# Notes for s390x: the VM is a z17 (machine 9175); llama.cpp emits -march=arch15 which gcc 13 does not
# know, so we pin -march=z16 (VXE2 still enabled). Little-endian GGUFs do not load on big-endian hosts;
# fetch_model.sh converts with gguf-py's gguf_convert_endian.py (patched for numpy 1.26).
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
ARG LLAMA_REF=master
RUN git clone --depth 1 --branch ${LLAMA_REF} https://github.com/ggml-org/llama.cpp /src \
 && sed -i 's/-march=arch15/-march=z16/' /src/ggml/src/ggml-cpu/CMakeLists.txt
WORKDIR /src
RUN cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build --config Release -j3 --target llama-server llama-bench llama-completion \
 && git rev-parse --short HEAD > /src/build/COMMIT

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive LD_LIBRARY_PATH=/app/bin
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 libstdc++6 ca-certificates curl python3 python3-numpy python3-tqdm python3-yaml \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/bin /app/bin
COPY --from=build /src/build/COMMIT /app/LLAMA_COMMIT
COPY --from=build /src/gguf-py /app/gguf-py
COPY fedaml/llm/fetch_model.sh /app/fetch_model.sh
RUN chmod +x /app/fetch_model.sh && sed -i 's/, copy=False)/)/' /app/gguf-py/gguf/scripts/gguf_convert_endian.py
ENV LLM_MODEL_FILE=qwen2.5-0.5b-instruct-q8_0-be.gguf LLM_THREADS=3 LLM_CTX=2048
VOLUME ["/models"]
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1
CMD ["/bin/sh", "-c", "exec /app/bin/llama-server -m /models/${LLM_MODEL_FILE} --host 0.0.0.0 --port 8080 -t ${LLM_THREADS} -c ${LLM_CTX} --no-webui"]
