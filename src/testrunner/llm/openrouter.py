"""OpenRouter LLM client implementation."""

import os
from typing import Optional

import httpx

from testrunner.llm.base import LLMClient, LLMResponse


class OpenRouterClient(LLMClient):
    """Client for OpenRouter API (OpenAI-compatible chat completions)."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen/qwen3-coder:free",
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 120,
    ):
        super().__init__()
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment "
                "variable, use api_key_file in config, or pass api_key parameter."
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                usage = data.get("usage")

                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    } if usage else None,
                    raw_response=data,
                )

        except httpx.TimeoutException:
            return LLMResponse(
                content="",
                model=self.model,
                raw_response={"error": "Request timed out"},
            )
        except httpx.HTTPStatusError as e:
            return LLMResponse(
                content="",
                model=self.model,
                raw_response={"error": f"HTTP error: {e.response.status_code}"},
            )
        except Exception as e:
            return LLMResponse(
                content="",
                model=self.model,
                raw_response={"error": str(e)},
            )

    def is_available(self) -> bool:
        """Check if OpenRouter API is reachable."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except Exception:
            return False
