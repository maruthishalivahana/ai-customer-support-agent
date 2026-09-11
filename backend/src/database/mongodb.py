"""MongoDB connection manager and lifecycle handler.

Provides connection pooling, ping health checks, and index initialization.
"""

from typing import Optional, Tuple
import pymongo
from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from src.config import get_settings, logger


class MongoDBManager:
    """Manages the lifecycle of the PyMongo connection client."""

    _instance: Optional["MongoDBManager"] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls) -> "MongoDBManager":
        """Singleton pattern for managing DB connections."""
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
        return cls._instance

    def connect(self) -> Database:
        """Establish connection to MongoDB and return the database object."""
        if self._db is not None:
            return self._db

        settings = get_settings()
        logger.info(
            "Connecting to MongoDB database '%s' at %s...",
            settings.MONGODB_DATABASE,
            settings.MONGODB_URI.split("@")[-1] if "@" in settings.MONGODB_URI else settings.MONGODB_URI,
        )

        self._client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGODB_TIMEOUT_MS,
        )
        self._db = self._client[settings.MONGODB_DATABASE]
        return self._db

    def close(self) -> None:
        """Close connection to MongoDB."""
        if self._client is not None:
            logger.info("Closing MongoDB connection.")
            self._client.close()
            self._client = None
            self._db = None

    def get_database(self) -> Database:
        """Return active database handle, connecting if not already connected."""
        if self._db is None:
            return self.connect()
        return self._db

    def ping(self) -> Tuple[bool, str]:
        """Perform a quick ping to test database connectivity without hanging.

        Returns:
            Tuple[bool, str]: (is_healthy, status_message)
        """
        try:
            db = self.get_database()
            # PyMongo command to ping the server
            db.command("ping")
            return True, "MongoDB connection established and responsive."
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            logger.warning("MongoDB ping failed: %s", exc)
            return False, f"Connection failure: {str(exc)}"
        except Exception as exc:
            logger.error("Unexpected error during MongoDB ping: %s", exc)
            return False, f"Unexpected error: {str(exc)}"

    def init_indexes(self) -> None:
        """Create required indexes on collections for fast query and integrity."""
        try:
            db = self.get_database()

            # 1. support_cases indexes
            db.support_cases.create_index([("case_id", ASCENDING)], unique=True, name="idx_case_id_unique")
            db.support_cases.create_index([("conversation_id", ASCENDING)], name="idx_case_conv_id")
            db.support_cases.create_index([("created_at", ASCENDING)], name="idx_case_created_at")

            # 2. conversations indexes
            db.conversations.create_index([("conversation_id", ASCENDING)], unique=True, name="idx_conv_id_unique")
            db.conversations.create_index([("created_at", ASCENDING)], name="idx_conv_created_at")

            # 3. predictions indexes
            db.predictions.create_index([("intent", ASCENDING)], name="idx_pred_intent")
            db.predictions.create_index([("created_at", ASCENDING)], name="idx_pred_created_at")

            logger.info("Successfully initialized MongoDB indexes.")
        except Exception as exc:
            logger.warning("Could not initialize MongoDB indexes (DB may be offline): %s", exc)


# Global instance
mongo_manager = MongoDBManager()


def get_db() -> Database:
    """Dependency provider for FastAPI route endpoints."""
    return mongo_manager.get_database()
