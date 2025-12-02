"""
Production-Grade Logging Module for VeloData.

Architecture:
- Structured logging (JSON format for production)
- Multiple handlers (console + rotating file)
- Service-specific loggers with isolated log files
- Environment-aware configuration
- Correlation ID support for distributed tracing
- Performance optimized with lazy evaluation

Best Practices Applied:
1. DRY: Single source of truth for logging config
2. Separation of Concerns: Core module, services consume
3. 12-Factor App: Environment-based configuration
4. Observability: Structured, queryable logs
5. Production-Ready: Rotation, levels, formatting
"""

import logging
import sys
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
import os


# Project root and logs directory
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    Outputs logs in JSON format for easy parsing by log aggregators.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (e.g., correlation_id, user_id)
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        if hasattr(record, "extra"):
            log_data["extra"] = record.extra

        return json.dumps(log_data)


class ColoredConsoleFormatter(logging.Formatter):
    """
    Colored console formatter for development.
    Makes logs readable in terminal with color coding.
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname:8}{self.RESET}"
        return super().format(record)


def get_logger(
    service_name: str,
    log_level: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_json: bool = False,
) -> logging.Logger:
    """
    Get a configured logger for a service.

    Args:
        service_name: Name of the service (e.g., 'seeder', 'api', 'worker')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Enable console output
        enable_file: Enable file output with rotation
        enable_json: Use JSON format (for production)

    Returns:
        Configured logger instance

    Usage:
        logger = get_logger('seeder')
        logger.info('Processing started', extra={'correlation_id': '12345'})
    """
    # Determine log level from env or parameter
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Determine environment
    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_production = environment == "production"

    # Use JSON format in production unless explicitly disabled
    if is_production and enable_json is None:
        enable_json = True

    # Create logger
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level))
    logger.handlers.clear()  # Clear existing handlers to avoid duplicates

    # Console Handler (for development and debugging)
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))

        if enable_json:
            console_formatter = StructuredFormatter()
        else:
            console_formatter = ColoredConsoleFormatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File Handler with Rotation (always use for persistence)
    if enable_file:
        log_file = LOGS_DIR / f"{service_name}.log"

        # Rotating file handler: 10MB per file, keep 5 backups
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, log_level))

        # Always use JSON format for file logs (easier to parse)
        if enable_json or is_production:
            file_formatter = StructuredFormatter()
        else:
            file_formatter = logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def log_execution_time(logger: logging.Logger):
    """
    Decorator to log function execution time.

    Usage:
        @log_execution_time(logger)
        def my_function():
            pass
    """
    import functools
    import time

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    f"{func.__name__} executed successfully",
                    extra={"execution_time_seconds": execution_time},
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"{func.__name__} failed after {execution_time:.2f}s",
                    exc_info=True,
                    extra={"execution_time_seconds": execution_time},
                )
                raise

        return wrapper

    return decorator


# Example usage and testing
if __name__ == "__main__":
    # Test the logger
    test_logger = get_logger("test-service", log_level="DEBUG")

    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")

    # Test with extra context
    test_logger.info(
        "User action",
        extra={"correlation_id": "abc-123", "user_id": "user-456", "action": "login"},
    )

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except ValueError:
        test_logger.exception("An error occurred during processing")

    print(f"\nLog file created at: {LOGS_DIR / 'test-service.log'}")
