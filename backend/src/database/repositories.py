"""Data access repositories isolating MongoDB operations from business logic.

AI and core modules interact only through these repository classes.
"""

from typing import Any, Dict, List, Optional
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from src.config import logger
from src.database.models import ConversationDoc, PredictionDoc, SupportCaseDoc
from src.database.mongodb import get_db
from src.schemas import SupportCaseCreate


class BaseRepository:
    """Base class for MongoDB collection repositories."""

    def __init__(self, collection_name: str, db: Optional[Database] = None) -> None:
        self._db = db if db is not None else get_db()
        self.collection_name = collection_name
        self.collection: Collection = self._db[collection_name]


class SupportCaseRepository(BaseRepository):
    """Repository handling persistence and queries for historical support cases."""

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__("support_cases", db)

    def insert_case(self, case: SupportCaseCreate) -> Optional[str]:
        """Insert a single support case. Returns inserted ID or None if duplicate."""
        doc = SupportCaseDoc(**case.model_dump()).to_mongo_dict()
        try:
            result = self.collection.insert_one(doc)
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.debug("Duplicate case_id '%s' ignored.", case.case_id)
            return None
        except Exception as exc:
            logger.error("Failed to insert case '%s': %s", case.case_id, exc)
            raise

    def insert_many_cases(self, cases: List[SupportCaseCreate], ordered: bool = False) -> int:
        """Bulk insert support cases, skipping duplicates if ordered=False.

        Returns:
            int: Number of successfully inserted documents.
        """
        if not cases:
            return 0

        docs = [SupportCaseDoc(**c.model_dump()).to_mongo_dict() for c in cases]
        try:
            result = self.collection.insert_many(docs, ordered=ordered)
            return len(result.inserted_ids)
        except Exception as exc:
            # BulkWriteError often occurs when skipping duplicates; count inserted
            inserted_count = getattr(exc, "details", {}).get("nInserted", 0)
            logger.info("Bulk inserted %d cases (some duplicates skipped).", inserted_count)
            return inserted_count

    def find_by_case_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific support case by its unique case_id."""
        doc = self.collection.find_one({"case_id": case_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def find_by_conversation_id(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Retrieve all support cases belonging to a specific conversation path."""
        cursor = self.collection.find({"conversation_id": conversation_id})
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    def count_cases(self) -> int:
        """Count total support cases stored in the database."""
        return self.collection.count_documents({})

    def fetch_all(self, limit: int = 50000) -> List[Dict[str, Any]]:
        """Fetch all support cases up to limit, useful for index re-building."""
        cursor = self.collection.find({}, {"_id": 0}).limit(limit)
        return list(cursor)


class ConversationRepository(BaseRepository):
    """Repository handling reconstructed conversations."""

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__("conversations", db)

    def save_conversation(self, conv: ConversationDoc) -> str:
        """Save a reconstructed conversation document."""
        doc = conv.to_mongo_dict()
        try:
            self.collection.update_one(
                {"conversation_id": conv.conversation_id},
                {"$set": doc},
                upsert=True,
            )
            return conv.conversation_id
        except Exception as exc:
            logger.error("Failed to save conversation '%s': %s", conv.conversation_id, exc)
            raise

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a conversation by ID."""
        doc = self.collection.find_one({"conversation_id": conversation_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def count_conversations(self) -> int:
        """Count total conversations."""
        return self.collection.count_documents({})


class PredictionRepository(BaseRepository):
    """Repository handling prediction and agent escalation telemetry logging."""

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__("predictions", db)

    def log_prediction(self, prediction: PredictionDoc) -> str:
        """Log an agent prediction run into the database."""
        doc = prediction.to_mongo_dict()
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent prediction records."""
        cursor = self.collection.find().sort("created_at", -1).limit(limit)
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    def count_predictions(self) -> int:
        """Return total logged predictions."""
        return self.collection.count_documents({})
