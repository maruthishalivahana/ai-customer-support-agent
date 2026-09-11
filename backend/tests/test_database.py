"""Unit tests for MongoDB repositories using mongomock for isolated execution."""

import mongomock
import pytest

from src.database.models import ConversationDoc, ConversationTurnDoc, PredictionDoc
from src.database.repositories import (
    ConversationRepository,
    PredictionRepository,
    SupportCaseRepository,
)
from src.schemas import SupportCaseCreate


@pytest.fixture
def mock_db():
    """Create an isolated in-memory mongomock database instance."""
    client = mongomock.MongoClient()
    db = client["test_hiver_support"]
    # Create unique index for testing
    db.support_cases.create_index("case_id", unique=True)
    db.conversations.create_index("conversation_id", unique=True)
    return db


def test_support_case_repository_insert_and_find(mock_db):
    """Test inserting and finding a support case in the repository."""
    repo = SupportCaseRepository(db=mock_db)

    case = SupportCaseCreate(
        case_id="case_1001",
        conversation_id="conv_500",
        customer_message="My screen is unresponsive.",
        apple_support_response="Please perform a force restart.",
        conversation_context="Context turn",
        created_at="2017-10-11T09:00:00Z",
    )

    inserted_id = repo.insert_case(case)
    assert inserted_id is not None

    # Retrieve by case_id
    found = repo.find_by_case_id("case_1001")
    assert found is not None
    assert found["case_id"] == "case_1001"
    assert found["customer_message"] == "My screen is unresponsive."
    assert found["apple_support_response"] == "Please perform a force restart."
    assert isinstance(found["_id"], str)


def test_support_case_repository_bulk_insert_and_count(mock_db):
    """Test bulk insertion and counting in SupportCaseRepository."""
    repo = SupportCaseRepository(db=mock_db)

    cases = [
        SupportCaseCreate(
            case_id=f"case_{i}",
            conversation_id=f"conv_{i // 2}",
            customer_message=f"Problem {i}",
            apple_support_response=f"Solution {i}",
        )
        for i in range(5)
    ]

    count = repo.insert_many_cases(cases)
    assert count == 5
    assert repo.count_cases() == 5

    # Check finding by conversation_id
    conv_cases = repo.find_by_conversation_id("conv_0")
    assert len(conv_cases) == 2


def test_conversation_repository(mock_db):
    """Test saving and retrieving conversation documents."""
    repo = ConversationRepository(db=mock_db)

    conv = ConversationDoc(
        conversation_id="conv_alpha",
        message_count=2,
        turns=[
            ConversationTurnDoc(
                tweet_id="t1",
                author_id="user1",
                inbound=True,
                text="Help my phone crashed",
            ),
            ConversationTurnDoc(
                tweet_id="t2",
                author_id="AppleSupport",
                inbound=False,
                text="We are here to help.",
            ),
        ],
    )

    conv_id = repo.save_conversation(conv)
    assert conv_id == "conv_alpha"

    retrieved = repo.get_conversation("conv_alpha")
    assert retrieved is not None
    assert retrieved["conversation_id"] == "conv_alpha"
    assert retrieved["message_count"] == 2
    assert len(retrieved["turns"]) == 2


def test_prediction_repository(mock_db):
    """Test logging and retrieving predictions."""
    repo = PredictionRepository(db=mock_db)

    pred = PredictionDoc(
        message="My battery is dead",
        intent="Battery / Charging",
        intent_confidence=0.95,
        draft_reply="Please visit an Apple Authorized Service Provider.",
        escalate=False,
        escalation_reason="High confidence match.",
        evidence=[{"case_id": "c1", "similarity": 0.89}],
    )

    inserted_id = repo.log_prediction(pred)
    assert inserted_id is not None

    recent = repo.get_recent(limit=10)
    assert len(recent) == 1
    assert recent[0]["intent"] == "Battery / Charging"
    assert recent[0]["intent_confidence"] == 0.95
    assert isinstance(recent[0]["_id"], str)
