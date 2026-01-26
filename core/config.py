"""
Configuration loader for VeloData.
Loads environment variables from .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv


# Load .env from the project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


class Config:
    """Application configuration."""

    # Database
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/velodata")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "velodata")

    # LLM Configuration
    # OpenRouter (preferred - cloud-based, no local setup required)
    OPEN_ROUTER_API_KEY: str = os.getenv("OPEN_ROUTER_API_KEY", "")
    OPEN_ROUTER_BASE_URL: str = os.getenv("OPEN_ROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Ollama (fallback - requires local installation)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Model settings (used by both providers)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "google/gemini-2.0-flash-exp:free")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))


# Singleton instance
config = Config()
