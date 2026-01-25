"""
LLM Client - Abstract interface for LLM providers.

This module defines the contract for LLM providers and implements
concrete adapters for different backends (Ollama, OpenAI, etc.).

Design Patterns:
    - Strategy Pattern: Different LLM providers implement same interface
    - Factory Pattern: get_llm_client() creates appropriate client
    - Adapter Pattern: Each provider adapter normalizes responses

Example:
    client = get_llm_client()  # Returns configured OllamaClient
    response = client.generate("Translate: こんにちは")
    print(response.content)
"""

import os
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
import urllib.request
import urllib.error

from core.logging import get_logger

logger = get_logger("llm-client")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class LLMResponse:
    """
    Normalized response from any LLM provider.

    Attributes:
        content: The generated text response
        model: Model that generated the response
        tokens_used: Total tokens consumed (prompt + completion)
        latency_ms: Response time in milliseconds
        raw_response: Original response from provider (for debugging)
    """
    content: str
    model: str
    tokens_used: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        """Check if response contains valid content."""
        return bool(self.content and self.content.strip())


@dataclass
class LLMConfig:
    """
    Configuration for LLM client.

    Attributes:
        model: Model identifier (e.g., "qwen2.5:7b", "gpt-4")
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
        max_tokens: Maximum tokens to generate
        timeout: Request timeout in seconds
        base_url: API base URL
    """
    model: str = "qwen2.5:7b"
    temperature: float = 0.1  # Low for deterministic tasks like translation
    max_tokens: int = 1024
    timeout: int = 60
    base_url: str = "http://localhost:11434"

    # Additional provider-specific options
    options: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ABSTRACT BASE CLASS
# ============================================================================

class LLMClient(ABC):
    """
    Abstract base class for LLM providers.

    Subclasses must implement:
        - generate(): Core text generation method
        - is_available(): Check if provider is accessible

    This abstraction allows swapping providers without changing task code.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize client with configuration.

        Args:
            config: LLM configuration (uses defaults if not provided)
        """
        self.config = config or LLMConfig()

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text from prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            **kwargs: Provider-specific options

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the LLM provider is accessible.

        Returns:
            True if provider is available and responding
        """
        pass

    def generate_batch(
        self,
        prompts: List[str],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> List[LLMResponse]:
        """
        Generate responses for multiple prompts.

        Default implementation processes sequentially.
        Subclasses may override for parallel processing.

        Args:
            prompts: List of prompts
            system_prompt: Optional system instructions
            **kwargs: Provider-specific options

        Returns:
            List of LLMResponse objects
        """
        return [
            self.generate(prompt, system_prompt, **kwargs)
            for prompt in prompts
        ]


# ============================================================================
# OLLAMA CLIENT
# ============================================================================

class OllamaClient(LLMClient):
    """
    Ollama LLM client implementation.

    Connects to local Ollama instance via REST API.
    Supports all Ollama-compatible models (Qwen, Gemma, Llama, etc.).

    Example:
        client = OllamaClient()
        response = client.generate(
            prompt="Translate to English: こんにちは",
            system_prompt="You are a translator."
        )
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize Ollama client."""
        super().__init__(config)
        self._api_url = f"{self.config.base_url}/api/generate"
        self._tags_url = f"{self.config.base_url}/api/tags"

    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            req = urllib.request.Request(
                self._tags_url,
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                models = [m.get("name") for m in data.get("models", [])]
                return self.config.model in models
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text using Ollama API.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            **kwargs: Additional Ollama options

        Returns:
            LLMResponse with generated content
        """
        start_time = time.time()

        # Build request payload
        payload = {
            "model": kwargs.get("model", self.config.model),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                **self.config.options,
                **kwargs.get("options", {})
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            # Make request
            req = urllib.request.Request(
                self._api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                raw_response = json.loads(response.read().decode())

            latency_ms = (time.time() - start_time) * 1000

            # Extract response data
            content = raw_response.get("response", "")
            eval_count = raw_response.get("eval_count")
            prompt_eval_count = raw_response.get("prompt_eval_count")

            logger.debug(
                "Ollama generation complete",
                extra={
                    "model": self.config.model,
                    "latency_ms": round(latency_ms, 2),
                    "tokens": eval_count,
                }
            )

            return LLMResponse(
                content=content.strip(),
                model=self.config.model,
                tokens_used=(prompt_eval_count or 0) + (eval_count or 0),
                prompt_tokens=prompt_eval_count,
                completion_tokens=eval_count,
                latency_ms=latency_ms,
                raw_response=raw_response
            )

        except urllib.error.URLError as e:
            logger.error(f"Ollama request failed: {e}")
            return LLMResponse(
                content="",
                model=self.config.model,
                latency_ms=(time.time() - start_time) * 1000,
                raw_response={"error": str(e)}
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama response: {e}")
            return LLMResponse(
                content="",
                model=self.config.model,
                latency_ms=(time.time() - start_time) * 1000,
                raw_response={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected error in Ollama client: {e}", exc_info=True)
            return LLMResponse(
                content="",
                model=self.config.model,
                latency_ms=(time.time() - start_time) * 1000,
                raw_response={"error": str(e)}
            )


# ============================================================================
# CLIENT FACTORY
# ============================================================================

# Global client instance (lazy initialization)
_default_client: Optional[LLMClient] = None


def get_llm_client(
    provider: Literal["ollama"] = "ollama",
    config: Optional[LLMConfig] = None
) -> LLMClient:
    """
    Factory function to get configured LLM client.

    Uses singleton pattern for default client to reuse connections.

    Args:
        provider: LLM provider name
        config: Optional custom configuration

    Returns:
        Configured LLMClient instance

    Example:
        # Get default client (Ollama with qwen2.5:7b)
        client = get_llm_client()

        # Get client with custom model
        config = LLMConfig(model="gemma2:2b-instruct-q8_0")
        client = get_llm_client(config=config)
    """
    global _default_client

    # Return cached default client if no custom config
    if config is None and _default_client is not None:
        return _default_client

    # Build configuration from environment or defaults
    if config is None:
        config = LLMConfig(
            model=os.getenv("LLM_MODEL", "qwen2.5:7b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        )

    # Create client based on provider
    if provider == "ollama":
        client = OllamaClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # Cache default client
    if config is None:
        _default_client = client

    return client
