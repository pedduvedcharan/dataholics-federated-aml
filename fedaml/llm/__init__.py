"""GENAI runtime wrapper.

The only LLM runtime that works on the s390x (big-endian) LinuxONE VM is
llama.cpp built from source, serving a big-endian GGUF through ``llama-server``.
This package talks to that server over HTTP and never imports torch.

Environment knobs (all optional):
    LLM_URL            base URL of a running llama-server (default http://127.0.0.1:8080)
    LLM_MODEL_PATH     path to a big-endian GGUF; if set and no server answers, one is spawned
    LLAMA_SERVER_BIN   path to the llama-server binary (default: ``llama-server`` on PATH)
    LLM_THREADS        CPU threads for a spawned server (default 3)
"""
from fedaml.llm.client import LLMResult, LLMUnavailable, LlamaClient, generate

__all__ = ["LLMResult", "LLMUnavailable", "LlamaClient", "generate"]
