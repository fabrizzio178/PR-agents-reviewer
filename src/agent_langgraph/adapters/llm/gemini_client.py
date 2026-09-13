"""Gemini adapter: implements LLMClient on Google AI Studio's free tier."""

from __future__ import annotations

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiLLMClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            ),
        )
        return response.text or ""
