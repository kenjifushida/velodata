"""
MongoDB Database Connector (Singleton Pattern).
"""
from pymongo import MongoClient
from pymongo.database import Database
from core.config import config


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
        _db_client = MongoClient(config.MONGO_URI)
        _database = _db_client[config.DATABASE_NAME]
        print(f"[DATABASE] Connected to MongoDB: {config.DATABASE_NAME}")

    return _database


def close_db():
    """Close the database connection."""
    global _db_client, _database

    if _db_client:
        _db_client.close()
        _db_client = None
        _database = None
        print("[DATABASE] Connection closed")
