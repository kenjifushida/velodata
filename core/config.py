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
    # Gemini (preferred - direct Google API, free tier available)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    # Ollama (fallback - requires local installation)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Model settings (used by all providers)
    # Free tier model options (Gemini AI Studio):
    #   gemini-2.5-flash-lite  → 15 RPM | 250,000 TPM | 1,000 RPD  (recommended)
    #   gemini-2.5-flash       → 10 RPM | 250,000 TPM |   250 RPD
    #   gemini-2.5-pro         →  5 RPM | 250,000 TPM |   100 RPD
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))


# Singleton instance
config = Config()
