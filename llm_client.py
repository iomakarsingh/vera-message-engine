"""
Thin LLM abstraction layer.
Supports OpenAI, Anthropic, Gemini, DeepSeek, Groq via environment variables.
Always uses temperature=0 for deterministic output.
"""

from __future__ import annotations

import json
import os
import time
from urllib import request as urlrequest, error as urlerror


# Defaults
DEFAULT_PROVIDER = "openai"
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini-1.5-flash",
    "deepseek": "deepseek-chat",
    "groq": "llama-3.3-70b-versatile",
}
LLM_TIMEOUT = 25  # seconds — leave 5s buffer for judge's 30s timeout


class LLMClient:
    """Unified LLM client with deterministic temperature=0."""

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER).lower()
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", DEFAULT_MODELS.get(self.provider, "gpt-4o"))

        if not self.api_key and self.provider != "ollama":
            raise ValueError(
                f"LLM_API_KEY environment variable required for provider '{self.provider}'. "
                "Set it before starting the server."
            )

    def complete(self, system_prompt: str, user_prompt: str, max_retries: int = 2) -> str:
        """
        Call the LLM and return the response text.
        Retries with exponential backoff on transient failures (429, 500, etc).
        """
        for attempt in range(max_retries + 1):
            try:
                return self._call(system_prompt, user_prompt)
            except Exception as e:
                if attempt < max_retries:
                    wait = 3.0 * (attempt + 1)  # 3s, 6s backoff for rate limits
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM call failed after {max_retries + 1} attempts: {e}")

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        elif self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        elif self.provider == "deepseek":
            return self._call_deepseek(system_prompt, user_prompt)
        elif self.provider == "groq":
            return self._call_groq(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urlrequest.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urlrequest.urlopen(req, timeout=LLM_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 2000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }).encode("utf-8")

        req = urlrequest.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
        )
        resp = urlrequest.urlopen(req, timeout=LLM_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return data["content"][0]["text"]

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        body = json.dumps({
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2000},
        }).encode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urlrequest.urlopen(req, timeout=LLM_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_deepseek(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urlrequest.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urlrequest.urlopen(req, timeout=LLM_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        """Groq — OpenAI-compatible API at api.groq.com. Uses requests lib (urllib blocked by Cloudflare)."""
        import requests as _requests

        resp = _requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "max_tokens": 2000,
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @property
    def info(self) -> str:
        return f"{self.provider}/{self.model}"
