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
# OPENROUTER CLIENT
# ============================================================================

class OpenRouterClient(LLMClient):
    """
    OpenRouter LLM client implementation.

    Connects to OpenRouter API (OpenAI-compatible) for access to various models
    including Google Gemini, Anthropic Claude, Meta Llama, etc.

    OpenRouter provides a unified API for multiple LLM providers with
    pay-per-token pricing and free tier models.

    Example:
        config = LLMConfig(
            model="google/gemini-2.0-flash-exp:free",
            base_url="https://openrouter.ai/api/v1"
        )
        client = OpenRouterClient(config, api_key="sk-or-...")
        response = client.generate(
            prompt="Translate to English: こんにちは",
            system_prompt="You are a translator."
        )
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize OpenRouter client.

        Args:
            config: LLM configuration
            api_key: OpenRouter API key (falls back to OPENROUTER_API_KEY env var)
        """
        # Set OpenRouter defaults before calling super().__init__
        if config is None:
            config = LLMConfig(
                model="google/gemini-2.0-flash-exp:free",
                base_url="https://openrouter.ai/api/v1",
                temperature=0.1,
                max_tokens=1024,
            )

        super().__init__(config)
        # Support both naming conventions for the API key
        self._api_key = api_key or os.getenv("OPEN_ROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPEN_ROUTER_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self._chat_url = f"{self.config.base_url}/chat/completions"
        self._models_url = f"{self.config.base_url}/models"

    def is_available(self) -> bool:
        """Check if OpenRouter API is accessible."""
        try:
            req = urllib.request.Request(
                self._models_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"OpenRouter not available: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text using OpenRouter API (OpenAI-compatible chat completions).

        Includes automatic retry with exponential backoff for rate limiting (429).

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            **kwargs: Additional options (max_retries, retry_delay)

        Returns:
            LLMResponse with generated content
        """
        start_time = time.time()
        max_retries = kwargs.get("max_retries", 3)
        base_delay = kwargs.get("retry_delay", 2.0)

        # Build messages array (OpenAI chat format)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Build request payload
        payload = {
            "model": kwargs.get("model", self.config.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Make request
                req = urllib.request.Request(
                    self._chat_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                        "HTTP-Referer": "https://velodata.io",  # Required by OpenRouter
                        "X-Title": "VeloData",  # Optional, for OpenRouter analytics
                    },
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                    raw_response = json.loads(response.read().decode())

                latency_ms = (time.time() - start_time) * 1000

                # Extract response data (OpenAI format)
                content = ""
                if raw_response.get("choices") and len(raw_response["choices"]) > 0:
                    content = raw_response["choices"][0].get("message", {}).get("content", "")

                usage = raw_response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                total_tokens = usage.get("total_tokens")

                logger.debug(
                    "OpenRouter generation complete",
                    extra={
                        "model": self.config.model,
                        "latency_ms": round(latency_ms, 2),
                        "tokens": total_tokens,
                        "attempts": attempt + 1,
                    }
                )

                return LLMResponse(
                    content=content.strip(),
                    model=raw_response.get("model", self.config.model),
                    tokens_used=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    raw_response=raw_response
                )

            except urllib.error.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.read().decode()
                except:
                    pass

                # Retry on rate limiting (429) or server errors (500, 502, 503)
                if e.code in (429, 500, 502, 503) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Server error ({e.code}), retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})",
                        extra={"model": self.config.model}
                    )
                    time.sleep(delay)
                    last_error = e
                    continue

                logger.error(
                    f"OpenRouter HTTP error: {e.code} - {error_body}",
                    extra={"status_code": e.code}
                )
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    latency_ms=(time.time() - start_time) * 1000,
                    raw_response={"error": str(e), "body": error_body}
                )

            except urllib.error.URLError as e:
                logger.error(f"OpenRouter request failed: {e}")
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    latency_ms=(time.time() - start_time) * 1000,
                    raw_response={"error": str(e)}
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenRouter response: {e}")
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    latency_ms=(time.time() - start_time) * 1000,
                    raw_response={"error": str(e)}
                )

            except Exception as e:
                logger.error(f"Unexpected error in OpenRouter client: {e}", exc_info=True)
                return LLMResponse(
                    content="",
                    model=self.config.model,
                    latency_ms=(time.time() - start_time) * 1000,
                    raw_response={"error": str(e)}
                )

        # All retries exhausted
        logger.error(
            f"All {max_retries + 1} attempts failed due to rate limiting",
            extra={"model": self.config.model}
        )
        return LLMResponse(
            content="",
            model=self.config.model,
            latency_ms=(time.time() - start_time) * 1000,
            raw_response={"error": "Rate limited after max retries", "last_error": str(last_error)}
        )


# ============================================================================
# CLIENT FACTORY
# ============================================================================

# Global client instance (lazy initialization)
_default_client: Optional[LLMClient] = None


def get_llm_client(
    provider: Optional[Literal["ollama", "openrouter"]] = None,
    config: Optional[LLMConfig] = None
) -> LLMClient:
    """
    Factory function to get configured LLM client.

    Uses singleton pattern for default client to reuse connections.
    Auto-detects provider based on environment variables:
        - If OPENROUTER_API_KEY is set, uses OpenRouter (default)
        - Otherwise falls back to local Ollama

    Args:
        provider: LLM provider name ("ollama" or "openrouter")
                  If None, auto-detects based on environment
        config: Optional custom configuration

    Returns:
        Configured LLMClient instance

    Example:
        # Get default client (auto-detects provider)
        client = get_llm_client()

        # Explicitly use OpenRouter
        client = get_llm_client(provider="openrouter")

        # Explicitly use Ollama with custom model
        config = LLMConfig(model="gemma2:2b-instruct-q8_0")
        client = get_llm_client(provider="ollama", config=config)
    """
    global _default_client

    # Return cached default client if no custom config and no explicit provider
    if config is None and provider is None and _default_client is not None:
        return _default_client

    # Auto-detect provider from environment if not specified
    if provider is None:
        if os.getenv("OPEN_ROUTER_API_KEY"):
            provider = "openrouter"
        else:
            provider = "ollama"

    # Create client based on provider
    if provider == "openrouter":
        # Build OpenRouter config from environment or defaults
        if config is None:
            config = LLMConfig(
                model=os.getenv("LLM_MODEL", "google/gemini-2.0-flash-exp:free"),
                base_url=os.getenv("OPEN_ROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
            )
        client = OpenRouterClient(config)
        logger.info(
            "Using OpenRouter LLM provider",
            extra={"model": config.model}
        )

    elif provider == "ollama":
        # Build Ollama config from environment or defaults
        if config is None:
            config = LLMConfig(
                model=os.getenv("LLM_MODEL", "qwen2.5:7b"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            )
        client = OllamaClient(config)
        logger.info(
            "Using Ollama LLM provider",
            extra={"model": config.model}
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # Cache as default client if using auto-detected defaults
    if _default_client is None:
        _default_client = client

    return client
