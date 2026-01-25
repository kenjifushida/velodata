"""
Translation Task - Japanese to English translation using LLM.

This module provides translation capabilities optimized for product titles
and descriptions from Japanese marketplaces.

Features:
    - Preserves product codes, model numbers, and technical terms
    - Handles mixed Japanese/English text
    - Maintains brand names and proper nouns
    - Batch translation support

Usage:
    # Using task class directly
    task = TranslationTask()
    result = task.execute("ワンピースカード ナミ PSA10")
    print(result.translated_text)  # "One Piece Card Nami PSA10"

    # Using convenience function
    from core.llm import translate
    english = translate("ポケモンカード ピカチュウex")
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import re

from core.llm.client import LLMClient, LLMResponse, get_llm_client
from core.llm.tasks.base import LLMTask, TaskResult
from core.logging import get_logger

logger = get_logger("llm-translation")


# ============================================================================
# RESULT CLASS
# ============================================================================

@dataclass
class TranslationResult(TaskResult):
    """
    Result of a translation task.

    Attributes:
        translated_text: The translated text
        source_text: Original source text
        source_language: Detected/specified source language
        target_language: Target language
        preserved_terms: Terms that were kept unchanged (codes, brands, etc.)
    """
    translated_text: str = ""
    source_text: str = ""
    source_language: str = "ja"
    target_language: str = "en"
    preserved_terms: List[str] = field(default_factory=list)

    @property
    def has_translation(self) -> bool:
        """Check if translation was produced."""
        return bool(self.translated_text and self.translated_text.strip())


# ============================================================================
# TRANSLATION TASK
# ============================================================================

class TranslationTask(LLMTask[TranslationResult]):
    """
    Japanese to English translation task.

    Optimized for translating product titles and descriptions from
    Japanese marketplaces while preserving:
        - Product codes (sv2a, OP09, etc.)
        - Model numbers (EOS R5, Z9, etc.)
        - Brand names (Rolex, Canon, etc.)
        - Grading information (PSA10, BGS 9.5, etc.)
        - Technical specifications

    Example:
        task = TranslationTask()

        # Translate product title
        result = task.execute("PSA10 ワンピースカード ナミ OP09")
        # Result: "PSA10 One Piece Card Nami OP09"

        # Translate with context for better accuracy
        result = task.execute(
            "美品 キヤノン EOS R5 ボディ",
            context="camera equipment"
        )
        # Result: "Excellent Condition Canon EOS R5 Body"
    """

    # Terms that should be preserved as-is during translation
    PRESERVE_PATTERNS = [
        r'\b[A-Z]{2,}\d+\b',           # PSA10, BGS9, OP09
        r'\b[A-Z]+[-/]?\d+[-/]?[A-Z]*\b',  # EOS-R5, sv2a, X-T5
        r'\b\d{5,}\b',                  # Long numbers (serial, cert numbers)
        r'#\d+',                        # Card numbers like #106
        r'\b[A-Z]{2,}\b',               # Acronyms: PSA, BGS, TCG
    ]

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        preserve_codes: bool = True
    ):
        """
        Initialize translation task.

        Args:
            client: LLM client instance
            preserve_codes: Whether to preserve product codes and numbers
        """
        super().__init__(client)
        self.preserve_codes = preserve_codes

    def get_system_prompt(self) -> str:
        """Get translation-specific system prompt."""
        return """You are a professional translator specializing in Japanese to English translation for e-commerce product listings.

Rules:
1. Translate Japanese text to natural English
2. PRESERVE these elements exactly as they appear:
   - Product codes (PSA10, sv2a, OP09, BGS 9.5)
   - Model numbers (EOS R5, Z9, A7R IV)
   - Brand names (Canon, Rolex, Louis Vuitton)
   - Technical specifications and numbers
3. Translate condition terms:
   - 美品 → Excellent Condition
   - 良品 → Good Condition
   - 並品 → Fair Condition
   - 新品 → New
   - 未使用 → Unused
   - 中古 → Used
4. Keep the translation concise - suitable for product titles
5. Output ONLY the translation, no explanations"""

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Build translation prompt.

        Args:
            text: Japanese text to translate
            context: Optional context hint (e.g., "trading cards", "watches")

        Returns:
            Formatted prompt
        """
        prompt = f"Translate to English:\n{text}"

        if context:
            prompt = f"[Context: {context}]\n{prompt}"

        return prompt

    def parse_response(
        self,
        response: LLMResponse,
        text: str,
        **kwargs
    ) -> TranslationResult:
        """
        Parse translation response.

        Args:
            response: LLM response
            text: Original source text

        Returns:
            TranslationResult with translated text
        """
        translated = response.content.strip()

        # Clean up common LLM artifacts
        # Remove quotes if the entire response is quoted
        if translated.startswith('"') and translated.endswith('"'):
            translated = translated[1:-1]
        if translated.startswith("'") and translated.endswith("'"):
            translated = translated[1:-1]

        # Remove "Translation:" prefix if present
        prefixes_to_remove = [
            "Translation:",
            "English:",
            "Here is the translation:",
            "The translation is:",
        ]
        for prefix in prefixes_to_remove:
            if translated.lower().startswith(prefix.lower()):
                translated = translated[len(prefix):].strip()

        # Find preserved terms
        preserved = self._find_preserved_terms(text)

        return TranslationResult(
            success=True,
            translated_text=translated,
            source_text=text,
            source_language="ja",
            target_language="en",
            preserved_terms=preserved
        )

    def _find_preserved_terms(self, text: str) -> List[str]:
        """
        Find terms that should be preserved during translation.

        Args:
            text: Source text

        Returns:
            List of terms to preserve
        """
        preserved = []
        for pattern in self.PRESERVE_PATTERNS:
            matches = re.findall(pattern, text)
            preserved.extend(matches)
        return list(set(preserved))

    def _create_error_result(
        self,
        error: str,
        response: Optional[LLMResponse] = None
    ) -> TranslationResult:
        """Create error result for translation task."""
        return TranslationResult(
            success=False,
            error=error,
            translated_text="",
            source_text="",
            latency_ms=response.latency_ms if response else None,
            model=response.model if response else None
        )

    def validate_input(self, text: str, **kwargs) -> Optional[str]:
        """Validate translation input."""
        if not text or not text.strip():
            return "Empty text provided for translation"
        if len(text) > 5000:
            return "Text too long (max 5000 characters)"
        return None

    def translate_batch(
        self,
        texts: List[str],
        context: Optional[str] = None
    ) -> List[TranslationResult]:
        """
        Translate multiple texts.

        Args:
            texts: List of Japanese texts
            context: Optional context hint

        Returns:
            List of TranslationResult objects
        """
        results = []
        for text in texts:
            result = self.execute(text, context=context)
            results.append(result)
        return results


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

# Cached task instance for convenience function
_default_task: Optional[TranslationTask] = None


def translate(
    text: str,
    context: Optional[str] = None,
    client: Optional[LLMClient] = None
) -> str:
    """
    Convenience function for quick translation.

    Args:
        text: Japanese text to translate
        context: Optional context hint
        client: Optional LLM client

    Returns:
        Translated English text (empty string if translation fails)

    Example:
        english = translate("ポケモンカード ピカチュウex sv2a")
        # Returns: "Pokemon Card Pikachu ex sv2a"
    """
    global _default_task

    if client is not None:
        task = TranslationTask(client)
    else:
        if _default_task is None:
            _default_task = TranslationTask()
        task = _default_task

    result = task.execute(text, context=context)

    if result.success:
        return result.translated_text
    else:
        logger.warning(f"Translation failed: {result.error}")
        return ""


def translate_batch(
    texts: List[str],
    context: Optional[str] = None,
    client: Optional[LLMClient] = None
) -> List[str]:
    """
    Translate multiple texts.

    Args:
        texts: List of Japanese texts
        context: Optional context hint
        client: Optional LLM client

    Returns:
        List of translated texts (empty strings for failed translations)
    """
    task = TranslationTask(client) if client else TranslationTask()
    results = task.translate_batch(texts, context=context)
    return [r.translated_text if r.success else "" for r in results]
