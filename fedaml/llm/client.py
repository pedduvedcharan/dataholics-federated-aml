"""HTTP client for a local llama.cpp ``llama-server`` (OpenAI-compatible API).

Design rules (agents/06-GENAI.md):
* hard wall-clock timeout, caller falls back to the template on ``LLMUnavailable``;
* no third-party HTTP library, only ``urllib`` so the genai container needs nothing extra;
* can spawn ``llama-server`` itself when ``LLM_MODEL_PATH`` is set and nothing answers.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("fedaml.llm")

DEFAULT_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080")
DEFAULT_THREADS = int(os.environ.get("LLM_THREADS", "3"))


class LLMUnavailable(RuntimeError):
    """Raised when no answer arrives in time; the caller must fall back."""


@dataclass
class LLMResult:
    """One completed generation plus the numbers the docs need."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float
    tokens_per_second: float
    raw: dict = field(default_factory=dict, repr=False)


class LlamaClient:
    """Minimal client for ``/health`` and ``/v1/chat/completions``."""

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self.url = url.rstrip("/")
        self._proc: subprocess.Popen | None = None

    # ---- availability -----------------------------------------------------
    def healthy(self, timeout: float = 2.0) -> bool:
        """True when a llama-server answers ``/health`` with status ok."""
        try:
            with urllib.request.urlopen(f"{self.url}/health", timeout=timeout) as r:
                return json.loads(r.read().decode()).get("status") == "ok"
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def ensure_server(self, wait_s: float = 90.0) -> bool:
        """Return True if a server answers; spawn one from ``LLM_MODEL_PATH`` if needed.

        A spawned server is a child of this process and dies with it.
        """
        if self.healthy():
            return True
        model = os.environ.get("LLM_MODEL_PATH")
        if not model or not os.path.exists(model):
            log.warning("no llama-server at %s and LLM_MODEL_PATH unset/missing", self.url)
            return False
        binary = os.environ.get("LLAMA_SERVER_BIN", "llama-server")
        host, port = _host_port(self.url)
        cmd = [binary, "-m", model, "--host", host, "--port", str(port), "-t", str(DEFAULT_THREADS),
               "-c", "2048", "--no-webui", "--log-disable"]
        log.info("spawning %s", " ".join(cmd))
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning("cannot start llama-server: %s", e)
            return False
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.healthy():
                log.info("llama-server ready after %.1fs", time.time() - t0)
                return True
            if self._proc.poll() is not None:
                log.warning("llama-server exited with code %s", self._proc.returncode)
                return False
            time.sleep(1.0)
        log.warning("llama-server did not become healthy in %.0fs", wait_s)
        return False

    def stop(self) -> None:
        """Terminate a server this client spawned (no-op otherwise)."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    # ---- generation -------------------------------------------------------
    def chat(self, system: str, user: str, *, max_tokens: int = 400, temperature: float = 0.2,
             timeout: float = 60.0, seed: int = 42, json_mode: bool = False) -> LLMResult:
        """One chat completion. Raises ``LLMUnavailable`` on timeout or transport error."""
        body: dict = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise LLMUnavailable(f"llama-server at {self.url}: {e}") from e
        dt = time.time() - t0
        usage = data.get("usage", {})
        comp = int(usage.get("completion_tokens", 0))
        text = data["choices"][0]["message"]["content"] if data.get("choices") else ""
        return LLMResult(
            text=text,
            model=str(data.get("model", "")),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=comp,
            seconds=dt,
            tokens_per_second=(comp / dt) if dt > 0 else 0.0,
            raw=data,
        )


def generate(system: str, user: str, **kw) -> LLMResult:
    """Convenience wrapper: ensure a server, then one chat completion."""
    client = LlamaClient()
    if not client.ensure_server():
        raise LLMUnavailable(f"no llama-server reachable at {client.url}")
    return client.chat(system, user, **kw)


def _host_port(url: str) -> tuple[str, int]:
    hp = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = hp.partition(":")
    return host or "127.0.0.1", int(port or 8080)
