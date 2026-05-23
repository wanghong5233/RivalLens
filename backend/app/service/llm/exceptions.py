from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for LLM service failures."""


class LLMRequestError(LLMError):
    """Raised when provider request fails."""


class LLMResponseFormatError(LLMError):
    """Raised when provider response is not valid JSON object content."""
