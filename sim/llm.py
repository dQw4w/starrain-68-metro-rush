"""Talking to a local model.

Ollama and LM Studio both serve an OpenAI-compatible /v1/chat/completions,
so one client covers both — only the base URL and model name differ:

    ollama     http://127.0.0.1:11434/v1   (model e.g. "qwen2.5:7b")
    lm studio  http://127.0.0.1:1234/v1    (model = whatever is loaded)

Note the literal 127.0.0.1 rather than "localhost": on macOS localhost
resolves to ::1 first, and anything else holding that port on IPv6 (a stray
Docker publish, say) silently swallows the request — which shows up as a
baffling "model not found" for a model you definitely pulled.

stdlib only, so `sim/` needs nothing installed beyond Python.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMConfig:
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:7b"
    temperature: float = 0.7
    timeout_s: float = 120.0
    #: Printed prompts/replies are the only way to see why an agent did
    #: something daft, so this is worth having on for a single game.
    verbose: bool = False


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.calls = 0

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.cfg.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            # The server's body is the useful part — a 404 here is almost
            # always "model not found", i.e. you haven't pulled it yet.
            detail = e.read().decode(errors="replace")[:300]
            raise LLMError(f"HTTP {e.code} from {self.cfg.base_url}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"local model unreachable at {self.cfg.base_url}: {e}") from e
        self.calls += 1
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected response shape: {body}") from e


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict | None:
    """Small local models wrap JSON in prose, ```json fences, or <think>
    blocks. Grab the outermost {...} and hope; the caller falls back to a
    heuristic if this returns None, so a bad reply costs a turn, not the run.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = _JSON_BLOCK.search(text)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
