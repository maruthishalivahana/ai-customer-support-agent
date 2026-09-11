"""Pytest configuration and global test fixtures.

Ensures the automated unit and integration test suite never depends on
live network calls to external OpenRouter endpoints.
"""

from unittest.mock import MagicMock
import pytest

from src.generator import get_response_generator


@pytest.fixture(autouse=True)
def mock_openrouter_for_tests(monkeypatch):
    """Ensure automated tests use a fast mocked LLM client without live HTTP traffic."""
    mock_choice = MagicMock()
    mock_choice.message.content = "AppleSupport response based on retrieved historical interactions."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    gen = get_response_generator()
    monkeypatch.setattr(gen, "_client", mock_client)

    try:
        from src.agent import _agent_instance
        if _agent_instance is not None and hasattr(_agent_instance, "generator"):
            monkeypatch.setattr(_agent_instance.generator, "_client", mock_client)
    except ImportError:
        pass
