"""
Base LLM Task - Abstract interface for LLM-powered tasks.

This module defines the contract for LLM tasks. Each task encapsulates:
    - Prompt engineering (system prompt, user prompt formatting)
    - Response parsing and validation
    - Error handling and fallbacks

Design Patterns:
    - Template Method: Base class defines execution flow, subclasses implement specifics
    - Strategy Pattern: Tasks can be swapped without changing calling code

Example:
    class MyTask(LLMTask[MyResult]):
        def build_prompt(self, text: str) -> str:
            return f"Process this: {text}"

        def parse_response(self, response: LLMResponse) -> MyResult:
            return MyResult(data=response.content)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Optional, Any, Dict
from datetime import datetime

from core.llm.client import LLMClient, LLMResponse, get_llm_client
from core.logging import get_logger

logger = get_logger("llm-task")


# ============================================================================
# BASE RESULT CLASS
# ============================================================================

@dataclass
class TaskResult:
    """
    Base class for task results.

    All task-specific result classes should inherit from this.

    Attributes:
        success: Whether the task completed successfully
        error: Error message if task failed
        latency_ms: Task execution time in milliseconds
        model: Model used for the task
        metadata: Additional task-specific metadata
    """
    success: bool = True
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        """Check if task failed."""
        return not self.success


# Type variable for generic result types
T = TypeVar("T", bound=TaskResult)


# ============================================================================
# ABSTRACT TASK CLASS
# ============================================================================

class LLMTask(ABC, Generic[T]):
    """
    Abstract base class for LLM-powered tasks.

    Subclasses must implement:
        - build_prompt(): Construct the prompt for the LLM
        - parse_response(): Parse LLM response into structured result
        - get_system_prompt(): Return system instructions (optional override)

    The execute() method orchestrates the flow:
        1. Build prompt from input
        2. Send to LLM via client
        3. Parse response into result

    Example:
        class SummarizationTask(LLMTask[SummaryResult]):
            def get_system_prompt(self) -> str:
                return "You are a text summarizer."

            def build_prompt(self, text: str) -> str:
                return f"Summarize: {text}"

            def parse_response(self, response: LLMResponse) -> SummaryResult:
                return SummaryResult(summary=response.content)
    """

    def __init__(self, client: Optional[LLMClient] = None):
        """
        Initialize task with LLM client.

        Args:
            client: LLM client instance (uses default if not provided)
        """
        self._client = client or get_llm_client()

    @property
    def client(self) -> LLMClient:
        """Get the LLM client."""
        return self._client

    @abstractmethod
    def build_prompt(self, *args, **kwargs) -> str:
        """
        Build the prompt to send to the LLM.

        Args:
            *args, **kwargs: Task-specific arguments

        Returns:
            Formatted prompt string
        """
        pass

    @abstractmethod
    def parse_response(self, response: LLMResponse, *args, **kwargs) -> T:
        """
        Parse LLM response into structured result.

        Args:
            response: Raw LLM response
            *args, **kwargs: Original task arguments for context

        Returns:
            Parsed task result
        """
        pass

    def get_system_prompt(self) -> Optional[str]:
        """
        Get system prompt for the task.

        Override in subclass to provide task-specific system instructions.

        Returns:
            System prompt string or None
        """
        return None

    def validate_input(self, *args, **kwargs) -> Optional[str]:
        """
        Validate task inputs before execution.

        Override in subclass to add input validation.

        Args:
            *args, **kwargs: Task-specific arguments

        Returns:
            Error message if validation fails, None if valid
        """
        return None

    def execute(self, *args, **kwargs) -> T:
        """
        Execute the task.

        Orchestrates the full task flow:
            1. Validate inputs
            2. Build prompt
            3. Generate LLM response
            4. Parse and return result

        Args:
            *args, **kwargs: Task-specific arguments

        Returns:
            Parsed task result
        """
        # Validate inputs
        validation_error = self.validate_input(*args, **kwargs)
        if validation_error:
            logger.warning(f"Task input validation failed: {validation_error}")
            return self._create_error_result(validation_error)

        try:
            # Build prompt
            prompt = self.build_prompt(*args, **kwargs)
            system_prompt = self.get_system_prompt()

            # Generate response
            response = self._client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                **kwargs.get("llm_options", {})
            )

            # Check for LLM errors
            if not response.success:
                error_msg = response.raw_response.get("error", "LLM generation failed")
                logger.error(f"LLM generation failed: {error_msg}")
                return self._create_error_result(error_msg, response)

            # Parse response
            result = self.parse_response(response, *args, **kwargs)

            # Add metadata
            result.latency_ms = response.latency_ms
            result.model = response.model

            return result

        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            return self._create_error_result(str(e))

    def _create_error_result(
        self,
        error: str,
        response: Optional[LLMResponse] = None
    ) -> T:
        """
        Create an error result.

        Subclasses should override to return their specific result type.

        Args:
            error: Error message
            response: Optional LLM response for context

        Returns:
            Error result instance
        """
        # Default implementation - subclasses should override
        return TaskResult(
            success=False,
            error=error,
            latency_ms=response.latency_ms if response else None,
            model=response.model if response else None
        )
