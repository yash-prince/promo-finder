"""One tiny wrapper around LiteLLM. To change the model, change the MODEL string — nothing else.

Examples:  gemini/gemini-3-flash-preview | groq/llama-3.3-70b-versatile | openai/gpt-4o-mini | anthropic/claude-sonnet-4-5
Keys are read from environment variables (GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY)
or from a local .env file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

DEFAULT_MODEL = "gemini/gemini-3-flash-preview"
CACHE_DIR = Path(__file__).parent / ".cache"

_lock = threading.Lock()
_last_call = 0.0


def load_env() -> None:
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def _throttle(rpm: int) -> None:
    """Free tiers allow only a few requests per minute; space the calls out."""
    global _last_call
    with _lock:
        wait = 60.0 / rpm - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)      # model added chatter around the JSON
        if m:
            return json.loads(m.group(0))
        raise


def ask_json(system: str, user: str, model: str = DEFAULT_MODEL, rpm: int = 8,
             use_cache: bool = True, temperature: float = 0.3) -> dict:
    """Send a prompt, get back parsed JSON. Cached on disk so re-runs are free and deterministic."""
    key = hashlib.sha256(json.dumps([model, system, user, temperature]).encode()).hexdigest()[:24]
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    import litellm
    litellm.suppress_debug_info = True
    litellm.drop_params = True      # different models accept different params; ignore unsupported ones
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            _throttle(rpm)
            resp = litellm.completion(
                model=model, temperature=temperature, timeout=240,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            data = _parse_json(resp.choices[0].message.content)
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as e:           # rate limit, bad JSON, network blip -> back off and retry
            last_err = e
            print(f"  [llm retry {attempt + 1}/5] {str(e).splitlines()[0][:160]}", flush=True)
            time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")
