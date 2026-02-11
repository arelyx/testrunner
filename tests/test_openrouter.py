"""Tests for the OpenRouter LLM client."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from testrunner.llm.openrouter import OpenRouterClient


@pytest.fixture
def client():
    """Create an OpenRouter client with a test API key."""
    return OpenRouterClient(api_key="test-key", model="test/model:free")


class TestOpenRouterClient:
    """Tests for OpenRouterClient."""

    def test_requires_api_key(self):
        """Test that missing API key raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key required"):
                OpenRouterClient(api_key="")

    def test_api_key_from_env(self):
        """Test API key can be loaded from environment variable."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-key"}):
            client = OpenRouterClient()
            assert client.api_key == "env-key"

    def test_api_key_param_takes_precedence(self):
        """Test that explicit api_key parameter overrides env var."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-key"}):
            client = OpenRouterClient(api_key="param-key")
            assert client.api_key == "param-key"

    def test_default_model(self):
        """Test default model is a free Llama model."""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"}):
            client = OpenRouterClient()
            assert ":free" in client.model

    def test_headers(self, client):
        """Test authorization headers."""
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_generate_success(self, client):
        """Test successful generation."""
        mock_response = {
            "choices": [
                {"message": {"content": "Hello, world!"}}
            ],
            "model": "test/model:free",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
        }

        mock_http = MagicMock()
        mock_http.json.return_value = mock_response
        mock_http.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(
                post=MagicMock(return_value=mock_http)
            ))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            response = client.generate("test prompt")

            assert response.content == "Hello, world!"
            assert response.model == "test/model:free"
            assert response.usage["prompt_tokens"] == 10

    def test_generate_with_system_prompt(self, client):
        """Test that system prompt is included in messages."""
        mock_response = {
            "choices": [{"message": {"content": "response"}}],
            "model": "test/model:free",
        }

        mock_http = MagicMock()
        mock_http.json.return_value = mock_response
        mock_http.raise_for_status = MagicMock()

        mock_post = MagicMock(return_value=mock_http)

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(
                post=mock_post
            ))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            client.generate("user prompt", system_prompt="system prompt")

            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert len(payload["messages"]) == 2
            assert payload["messages"][0]["role"] == "system"
            assert payload["messages"][1]["role"] == "user"

    def test_generate_timeout(self, client):
        """Test handling of timeout."""
        with patch("httpx.Client") as mock_client:
            mock_inner = MagicMock()
            mock_inner.post.side_effect = httpx.TimeoutException("timed out")
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_inner)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            response = client.generate("test")
            assert response.content == ""
            assert "timed out" in response.raw_response["error"]

    def test_generate_http_error(self, client):
        """Test handling of HTTP errors."""
        with patch("httpx.Client") as mock_client:
            mock_inner = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_inner.post.side_effect = httpx.HTTPStatusError(
                "rate limited", request=MagicMock(), response=mock_resp
            )
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_inner)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            response = client.generate("test")
            assert response.content == ""
            assert "429" in response.raw_response["error"]

    def test_is_available_success(self, client):
        """Test availability check when API is reachable."""
        with patch("httpx.Client") as mock_client:
            mock_inner = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_inner.get.return_value = mock_resp
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_inner)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            assert client.is_available() is True

    def test_is_available_failure(self, client):
        """Test availability check when API is unreachable."""
        with patch("httpx.Client") as mock_client:
            mock_inner = MagicMock()
            mock_inner.get.side_effect = Exception("connection refused")
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_inner)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            assert client.is_available() is False

    def test_generate_json_integration(self, client):
        """Test generate_json works through the base class."""
        mock_response = {
            "choices": [
                {"message": {"content": '{"key": "value"}'}}
            ],
            "model": "test/model:free",
        }

        mock_http = MagicMock()
        mock_http.json.return_value = mock_response
        mock_http.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(
                post=MagicMock(return_value=mock_http)
            ))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            result = client.generate_json("return JSON")
            assert result == {"key": "value"}
