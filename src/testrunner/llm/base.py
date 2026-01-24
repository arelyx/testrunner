"""Base LLM client interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Response from an LLM."""

    content: str
    model: str
    usage: Optional[dict[str, int]] = None
    raw_response: Optional[dict] = None

    @property
    def success(self) -> bool:
        return bool(self.content)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with the generated content
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        pass

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> Optional[dict[str, Any]]:
        """Generate a JSON response from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            temperature: Sampling temperature (lower for more deterministic JSON)

        Returns:
            Parsed JSON dict or None if parsing fails
        """
        import json

        # Add JSON instruction to the prompt
        json_prompt = f"{prompt}\n\nRespond with valid JSON only, no additional text."

        response = self.generate(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        if not response.success:
            return None

        # Try to extract JSON from the response
        content = response.content.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (```json and ```)
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            import re

            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return None
