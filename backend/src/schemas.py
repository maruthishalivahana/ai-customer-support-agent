"""Pydantic schemas for data validation, API requests, and responses.

Defines schemas for support cases, predictions, intent taxonomy, and health checks.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Intent(str, Enum):
    """The 12 canonical customer support intents for AppleSupport."""

    IOS_SOFTWARE = "iOS / Software"
    APP_ISSUE = "App Issue"
    DEVICE_HARDWARE = "Device / Hardware"
    MESSAGES_CALLING = "Messages / Calling"
    SETTINGS_FEATURES = "Settings / Features"
    BATTERY_CHARGING = "Battery / Charging"
    MUSIC_MEDIA = "Music / Media"
    CONNECTIVITY = "Connectivity"
    ICLOUD_BACKUP_DATA = "iCloud / Backup / Data"
    APPLE_ID_ACCOUNT = "Apple ID / Account"
    APP_STORE_PURCHASES = "App Store / Purchases"
    OTHER_GENERAL = "Other / General"


# Alias for backward compatibility
IntentEnum = Intent


# ==============================================================================
# Support Case Schemas (Historical Knowledge Base)
# ==============================================================================

class SupportCaseBase(BaseModel):
    """Base representation of an AppleSupport case."""

    case_id: str = Field(..., description="Unique case identifier (e.g. root tweet ID)")
    conversation_id: str = Field(..., description="ID of the conversation path")
    customer_message: str = Field(..., description="Customer problem or query text")
    apple_support_response: str = Field(..., description="Actual historical AppleSupport response")
    conversation_context: Optional[str] = Field(
        default=None,
        description="Prior conversation history if available",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Timestamp of the interaction in ISO or raw format",
    )

    @field_validator("customer_message", "apple_support_response")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        """Ensure critical text fields are not purely whitespace."""
        if not value or not value.strip():
            raise ValueError("Field cannot be empty or whitespace only.")
        return value.strip()


class SupportCaseCreate(SupportCaseBase):
    """Schema for creating a new support case in MongoDB."""
    pass


class SupportCaseInDB(SupportCaseBase):
    """Schema representing a support case retrieved from MongoDB."""
    id: Optional[str] = Field(default=None, alias="_id")

    model_config = {"populate_by_name": True}


# ==============================================================================
# Retrieval & Evidence Schemas
# ==============================================================================

class EvidenceItem(BaseModel):
    """A single retrieved historical case used as grounding evidence."""

    case_id: str
    conversation_id: str
    similarity: float = Field(..., ge=0.0, le=1.0, description="Cosine or vector similarity score")
    customer_message: str
    historical_response: str
    conversation_context: Optional[str] = None


class RetrieveRequest(BaseModel):
    """Request payload for historical case retrieval."""

    message: str = Field(..., min_length=1, description="Customer message or query")
    top_k: Optional[int] = Field(default=None, ge=1, le=10, description="Number of cases to retrieve")
    retriever: Optional[str] = Field(
        default=None,
        description="Retrieval engine: 'semantic' (FAISS embeddings) or 'tfidf' (lexical). Defaults to app setting.",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Customer message cannot be empty or blank whitespace.")
        return trimmed

    @field_validator("retriever")
    @classmethod
    def validate_retriever_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        norm_val = value.strip().lower()
        if norm_val not in ("semantic", "tfidf"):
            raise ValueError(f"Invalid retriever '{value}'. Must be 'semantic' or 'tfidf'.")
        return norm_val


class RetrievalResponse(BaseModel):
    """Response containing top retrieved cases."""

    query: str
    top_k: int
    retriever: Optional[str] = Field(
        default=None,
        description="Retrieval strategy used to generate results ('semantic' or 'tfidf')",
    )
    results: List[EvidenceItem] = []


# ==============================================================================
# Classification Schemas
# ==============================================================================

class IntentPredictionItem(BaseModel):
    """Intent prediction with confidence probability."""

    intent: IntentEnum
    confidence: float = Field(..., ge=0.0, le=1.0)


class ClassifyRequest(BaseModel):
    """Incoming request payload for intent classification."""

    message: str = Field(..., min_length=1, description="Customer message to classify")

    @field_validator("message")
    @classmethod
    def validate_message_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Customer message cannot be empty or blank whitespace.")
        return trimmed


class ClassificationResponse(BaseModel):
    """Full intent classification response."""

    intent: IntentEnum
    confidence: float = Field(..., ge=0.0, le=1.0)
    top_predictions: List[IntentPredictionItem] = []


# ==============================================================================
# Escalation Schemas
# ==============================================================================

class EscalationDecision(BaseModel):
    """Output of the escalation evaluation engine."""

    escalate: bool
    reason: str
    evidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ==============================================================================
# End-to-End Analysis API Schemas
# ==============================================================================

class AnalyzeRequest(BaseModel):
    """Incoming request to analyze a customer message."""

    message: str = Field(..., min_length=1, description="Incoming customer support inquiry")
    conversation_id: Optional[str] = Field(default=None, description="Optional tracking conversation ID")

    @field_validator("message")
    @classmethod
    def validate_message_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Customer message cannot be empty or blank whitespace.")
        return trimmed


class AnalyzeResponse(BaseModel):
    """End-to-end output returned by the agent and API."""

    intent: IntentEnum
    intent_confidence: float = Field(..., ge=0.0, le=1.0)
    draft_reply: str
    escalate: bool
    escalation_reason: str
    evidence: List[EvidenceItem] = []
    conversation_id: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ==============================================================================
# Health Check Schemas
# ==============================================================================

class DatabaseHealth(BaseModel):
    """Health status of the MongoDB database."""

    status: str = Field(..., description="'connected', 'disconnected', or 'error'")
    details: Optional[str] = None


class HealthResponse(BaseModel):
    """API health status and environment info."""

    status: str = "healthy"
    app_name: str
    version: str
    environment: str
    database: DatabaseHealth


# ==============================================================================
# Phase 6: Conversation & Decision Engine Schemas
# ==============================================================================

class SupportAction(str, Enum):
    """The three possible actions for the conversation-aware support decision engine."""

    AUTO_HANDLE = "auto_handle"
    CLARIFY = "clarify"
    ESCALATE = "escalate"


# Alias for backward compatibility and convenience
ActionEnum = SupportAction


class MessageRole(str, Enum):
    """Supported roles in a customer support conversation."""

    CUSTOMER = "customer"
    ASSISTANT = "assistant"


class MessageItem(BaseModel):
    """A single dialogue turn within a support conversation."""

    role: MessageRole = Field(..., description="Role of the turn author: 'customer' or 'assistant'")
    text: str = Field(..., min_length=1, description="Message text content")

    @field_validator("text")
    @classmethod
    def validate_text_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Message text cannot be empty or whitespace only.")
        return trimmed


class RetrievalSummary(BaseModel):
    """Concise metadata regarding the retrieval grounding results."""

    top_similarity: float = Field(..., ge=0.0, le=1.0, description="Highest cosine similarity score")
    top_k: int = Field(..., ge=0, description="Number of evidence items evaluated")


class DecisionSignals(BaseModel):
    """Explainable diagnostic signals informing the decision policy."""

    ambiguous: bool = Field(..., description="True if customer query lacks specific referents or details")
    evidence_sufficient: bool = Field(..., description="True if historical cases provide confident grounding")
    repeated_troubleshooting: bool = Field(..., description="True if customer indicated failed troubleshooting attempts")
    frustrated: bool = Field(default=False, description="True if customer expressed frustration signals (emoji, language)")
    resolved_closing: bool = Field(default=False, description="True if conversation is resolved or in closing state")


class AgentRequest(BaseModel):
    """Request payload for the conversation-aware support decision engine."""

    conversation_id: Optional[str] = Field(default=None, description="Optional conversation tracking ID")
    messages: List[MessageItem] = Field(..., min_length=1, description="Sequential dialogue turns in conversation")

    @field_validator("messages")
    @classmethod
    def validate_at_least_one_customer_message(cls, msgs: List[MessageItem]) -> List[MessageItem]:
        if not any(m.role == MessageRole.CUSTOMER for m in msgs):
            raise ValueError("Conversation must contain at least one message from the customer.")
        return msgs


class AgentResponse(BaseModel):
    """Output produced by the conversation-aware support decision engine."""

    conversation_id: Optional[str] = Field(default=None, description="Conversation tracking ID")
    action: SupportAction = Field(..., description="Selected decision policy action: auto_handle, clarify, or escalate")
    intent: IntentEnum = Field(..., description="Predicted customer problem intent")
    intent_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence probability of the intent")
    reason: str = Field(..., description="Concise explainable rationale for the chosen action")
    response: str = Field(
        default="",
        description="Natural-language support response generated for the customer",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Targeted clarification question if action is 'clarify', else null",
    )
    retrieval: RetrievalSummary = Field(..., description="Retrieval similarity summary")
    signals: DecisionSignals = Field(..., description="Underlying diagnostic policy signals")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Top retrieved grounding historical cases")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when decision was produced",
    )
