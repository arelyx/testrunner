"""Ollama LLM client implementation."""

import os
from typing import Optional

import httpx

from testrunner.llm.base import LLMClient, LLMResponse


class OllamaClient(LLMClient):
    """Client for Ollama LLM service."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: int = 120,
    ):
        """Initialize Ollama client.

        Args:
            base_url: Ollama API base URL
            model: Model name to use
            timeout: Request timeout in seconds
        """
        # Allow environment variable override
        self.base_url = os.environ.get("OLLAMA_HOST", base_url).rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from Ollama.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (num_predict in Ollama)

        Returns:
            LLMResponse with the generated content
        """
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()

                data = response.json()

                return LLMResponse(
                    content=data.get("response", ""),
                    model=data.get("model", self.model),
                    usage={
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                        "total_duration_ns": data.get("total_duration", 0),
                    },
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
        """Check if Ollama service is available."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models on the Ollama instance."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
        except Exception:
            return []

    def pull_model(self, model_name: Optional[str] = None) -> bool:
        """Pull a model from Ollama registry.

        Args:
            model_name: Model to pull (defaults to configured model)

        Returns:
            True if successful
        """
        model = model_name or self.model

        try:
            with httpx.Client(timeout=600) as client:  # Long timeout for download
                response = client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model, "stream": False},
                )
                return response.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature

        Returns:
            LLMResponse with the generated content
        """
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()

                data = response.json()
                message = data.get("message", {})

                return LLMResponse(
                    content=message.get("content", ""),
                    model=data.get("model", self.model),
                    usage={
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                    },
                    raw_response=data,
                )

        except Exception as e:
            return LLMResponse(
                content="",
                model=self.model,
                raw_response={"error": str(e)},
            )
