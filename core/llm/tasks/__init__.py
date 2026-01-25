"""
LLM Tasks Module

Contains specific task implementations that use LLM capabilities.
Each task encapsulates prompt engineering and response parsing.

Available Tasks:
    - TranslationTask: Japanese to English translation
    - (Future) ExtractionTask: Extract structured data from text
    - (Future) ClassificationTask: Classify products into categories
"""

from core.llm.tasks.base import LLMTask, TaskResult
from core.llm.tasks.translation import TranslationTask, TranslationResult, translate

__all__ = [
    "LLMTask",
    "TaskResult",
    "TranslationTask",
    "TranslationResult",
    "translate",
]
