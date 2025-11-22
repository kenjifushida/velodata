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
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/velodata")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "velodata")


# Singleton instance
config = Config()
