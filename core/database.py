"""
MongoDB Database Connector (Singleton Pattern).
"""
from pymongo import MongoClient
from pymongo.database import Database
from core.config import config
from core.logging import get_logger

# Initialize logger for database module
logger = get_logger("database")

_db_client: MongoClient | None = None
_database: Database | None = None


def get_db() -> Database:
    """
    Returns the MongoDB database instance (Singleton).

    Returns:
        Database: The MongoDB database object.
    """
    global _db_client, _database

    if _database is None:
        try:
            logger.info(f"Connecting to MongoDB", extra={"database": config.DATABASE_NAME})
            _db_client = MongoClient(config.MONGO_URI)
            _database = _db_client[config.DATABASE_NAME]
            logger.info(f"Successfully connected to MongoDB", extra={"database": config.DATABASE_NAME})
        except Exception as e:
            logger.error("Failed to connect to MongoDB", exc_info=True)
            raise

    return _database


def close_db():
    """Close the database connection."""
    global _db_client, _database

    if _db_client:
        try:
            _db_client.close()
            _db_client = None
            _database = None
            logger.info("Database connection closed")
        except Exception as e:
            logger.error("Error closing database connection", exc_info=True)
