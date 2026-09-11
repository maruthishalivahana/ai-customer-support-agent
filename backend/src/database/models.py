"""Database document models and serialization helpers for MongoDB collections."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SupportCaseDoc(BaseModel):
    """Document structure for the `support_cases` collection."""

    case_id: str
    conversation_id: str
    customer_message: str
    apple_support_response: str
    conversation_context: Optional[str] = None
    created_at: Optional[str] = None

    def to_mongo_dict(self) -> Dict[str, Any]:
        """Convert model to BSON-compatible dict."""
        return self.model_dump(exclude_none=True)


class ConversationTurnDoc(BaseModel):
    """Single turn inside a conversation."""

    tweet_id: str
    author_id: str
    inbound: bool
    text: str
    created_at: Optional[str] = None


class ConversationDoc(BaseModel):
    """Document structure for the `conversations` collection."""

    conversation_id: str
    message_count: int = 0
    turns: List[ConversationTurnDoc] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_mongo_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


class PredictionDoc(BaseModel):
    """Document structure for the `predictions` collection."""

    message: str
    intent: str
    intent_confidence: float
    draft_reply: str
    escalate: bool
    escalation_reason: str
    evidence: List[Dict[str, Any]] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_mongo_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)
