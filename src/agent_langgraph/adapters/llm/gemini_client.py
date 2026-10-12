"""Gemini adapter: implements LLMClient on Google AI Studio's free tier.

The response is constrained to a JSON schema, so a reply that does not parse
is an error the caller can see — never an empty, "clean" review.
"""

from __future__ import annotations

from google import genai
from google.genai import errors, types

from agent_langgraph.adapters.llm.schema import ReviewSchema, parse_review
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import LLMResult, TokenUsage

DEFAULT_MODEL = "gemini-2.5-flash"
_RETRYABLE_STATUS = [408, 429, 500, 502, 503, 504]


class GeminiLLMClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        client: genai.Client | None = None,
    ) -> None:
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=4,
                    initial_delay=2.0,
                    max_delay=30.0,
                    http_status_codes=_RETRYABLE_STATUS,
                )
            ),
        )
        self._model = model

    def review(self, system_prompt: str, user_prompt: str) -> LLMResult:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=ReviewSchema,
                    # No tools are passed; this only silences the SDK's AFC notice.
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except errors.APIError as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        usage = response.usage_metadata
        return LLMResult(
            items=parse_review(response.text or ""),
            usage=TokenUsage(
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            ),
        )
