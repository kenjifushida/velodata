"""
LLM Integration Module

Provides a clean, extensible architecture for integrating Large Language Models
into the VeloData platform. Designed with SOLID principles for maintainability
and extensibility.

Architecture:
    - LLMClient: Abstract base for LLM providers (Ollama, OpenAI, Anthropic, etc.)
    - LLMTask: Abstract base for specific tasks (translation, extraction, classification)
    - TaskRegistry: Central registry for discovering and executing tasks

Usage:
    from core.llm import get_llm_client, TranslationTask

    # Get configured client
    client = get_llm_client()

    # Execute translation task
    task = TranslationTask(client)
    result = task.execute("ワンピースカード ナミ", target_language="en")
    print(result.translated_text)

    # Or use the high-level API
    from core.llm import translate
    english_title = translate("ワンピースカード ナミ")
"""

from core.llm.client import LLMClient, LLMResponse, get_llm_client
from core.llm.tasks.base import LLMTask, TaskResult
from core.llm.tasks.translation import TranslationTask, TranslationResult, translate

__all__ = [
    # Client
    "LLMClient",
    "LLMResponse",
    "get_llm_client",
    # Tasks
    "LLMTask",
    "TaskResult",
    "TranslationTask",
    "TranslationResult",
    # High-level API
    "translate",
]
