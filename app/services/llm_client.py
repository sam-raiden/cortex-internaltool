"""Stage 21 -- thin, model-agnostic Ollama client.

Local-only by design: talks to a locally-running Ollama daemon over plain
HTTP JSON (default http://localhost:11434). No API key, no external network
call, no vendor SDK. Structural validity of the response is enforced by
Ollama's constrained decoding via the `format` JSON-schema parameter; the
caller (app/processing/llm_enrichment.py) still validates semantically
before persisting anything.
"""
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


class LLMError(Exception):
    """Raised after all retries are exhausted. Callers must catch this and
    degrade gracefully (persist a FAILED enrichment row) -- an LLM outage
    must never crash or block a caller that depends on deterministic data
    existing independently of this layer."""


class OllamaClient:
    def __init__(self, model: str = "qwen3:8b", base_url: str = None, timeout_seconds: int = 60):
        self.model = model
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout_seconds = timeout_seconds

    def generate_json(self, system_prompt: str, user_prompt: str, json_schema: dict, max_retries: int = 1) -> dict:
        """Calls the model with a JSON-schema-constrained response format
        and thinking disabled (qwen3 is a "thinking" model by default;
        `think: false` skips the chain-of-thought preamble and cuts latency
        substantially). Returns the parsed JSON dict. Raises LLMError if the
        request fails or the response isn't valid JSON after all retries."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": json_schema,
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                return json.loads(content)
            except Exception as e:
                last_error = e
                logger.warning(f"Ollama call failed (attempt {attempt + 1}/{max_retries + 1}, model={self.model}): {e}")

        raise LLMError(f"Ollama call failed after {max_retries + 1} attempt(s): {last_error}")
