"""Small wrapper around Gemini so the rest of the code only sees generate(prompt) -> text."""

import logging
import os
import time
from typing import Optional, Sequence

log = logging.getLogger("vibematch.llm")

# First model is the one I use; the second is a fallback when the first is overloaded (503).
DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")


class LLMError(RuntimeError):
    """Raised when no model could produce an answer."""


class GeminiClient:
    """Calls Gemini with a short retry and a fallback model."""

    def __init__(self, models: Sequence[str] = DEFAULT_MODELS, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set. Add it to .env or run with --offline.")
        from google import genai  # imported here so offline runs and tests don't need it

        self.client = genai.Client(api_key=key)
        self.models = list(models)
        self.calls = 0

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """Returns the model's text, trying each model up to twice before giving up."""
        last_error = None
        for model in self.models:
            for attempt in (1, 2):
                try:
                    self.calls += 1
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config={"temperature": temperature},
                    )
                    text = (response.text or "").strip()
                    log.info("llm ok model=%s attempt=%d chars=%d", model, attempt, len(text))
                    return text
                except Exception as exc:  # network, quota, 503 overload, unknown model
                    last_error = exc
                    log.warning("llm error model=%s attempt=%d: %s", model, attempt, str(exc)[:120])
                    time.sleep(1.5 * attempt)
        raise LLMError(f"All models failed: {last_error}")


class ScriptedLLM:
    """Fake client for tests: returns the given replies in order and records the prompts."""

    def __init__(self, replies: Sequence[str]):
        self.replies = list(replies)
        self.prompts = []
        self.calls = 0

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if not self.replies:
            raise LLMError("ScriptedLLM ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
