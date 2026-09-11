"""Unit tests for Pydantic domain schemas and request/response models."""

import pytest
from pydantic import ValidationError

from src.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DatabaseHealth,
    EvidenceItem,
    HealthResponse,
    Intent,
    IntentEnum,
    SupportCaseCreate,
)


def test_intent_taxonomy_has_exact_12_categories():
    """Verify that the intent taxonomy matches the exact 12 required categories."""
    expected_intents = {
        "iOS / Software",
        "App Issue",
        "Device / Hardware",
        "Messages / Calling",
        "Settings / Features",
        "Battery / Charging",
        "Music / Media",
        "Connectivity",
        "iCloud / Backup / Data",
        "Apple ID / Account",
        "App Store / Purchases",
        "Other / General",
    }
    actual_intents = {intent.value for intent in Intent}
    assert actual_intents == expected_intents
    assert len(Intent) == 12
    assert Intent is IntentEnum


def test_support_case_create_valid():
    """Verify valid support case instantiation."""
    case = SupportCaseCreate(
        case_id="101",
        conversation_id="conv_101",
        customer_message="My iPhone battery drains within 2 hours.",
        apple_support_response="We understand your concern. Which iOS version is installed?",
        conversation_context="Previous message: hello",
        created_at="2017-10-10T12:00:00Z",
    )
    assert case.case_id == "101"
    assert case.customer_message == "My iPhone battery drains within 2 hours."


def test_support_case_create_rejects_empty_and_whitespace():
    """Ensure empty or whitespace-only messages are rejected."""
    with pytest.raises(ValidationError):
        SupportCaseCreate(
            case_id="102",
            conversation_id="conv_102",
            customer_message="   ",
            apple_support_response="How can we help?",
        )

    with pytest.raises(ValidationError):
        SupportCaseCreate(
            case_id="103",
            conversation_id="conv_103",
            customer_message="Battery issue",
            apple_support_response="",
        )


def test_analyze_request_validation():
    """Test validation on incoming user analyze requests."""
    # Valid
    req = AnalyzeRequest(message="My AirPods won't connect.")
    assert req.message == "My AirPods won't connect."

    # Blank/whitespace
    with pytest.raises(ValidationError):
        AnalyzeRequest(message="")

    with pytest.raises(ValidationError):
        AnalyzeRequest(message="   \n\t  ")


def test_evidence_item_similarity_bounds():
    """Verify similarity score must be within [0.0, 1.0]."""
    # Valid
    ev = EvidenceItem(
        case_id="case_1",
        conversation_id="conv_1",
        similarity=0.88,
        customer_message="Battery issue",
        historical_response="Try updating iOS",
    )
    assert ev.similarity == 0.88

    # Invalid > 1.0
    with pytest.raises(ValidationError):
        EvidenceItem(
            case_id="case_1",
            conversation_id="conv_1",
            similarity=1.2,
            customer_message="test",
            historical_response="test",
        )

    # Invalid < 0.0
    with pytest.raises(ValidationError):
        EvidenceItem(
            case_id="case_1",
            conversation_id="conv_1",
            similarity=-0.05,
            customer_message="test",
            historical_response="test",
        )


def test_analyze_response_structure():
    """Test full end-to-end response model schema."""
    resp = AnalyzeResponse(
        intent=IntentEnum.BATTERY_CHARGING,
        intent_confidence=0.92,
        draft_reply="Please check your Battery Health in Settings > Battery.",
        escalate=False,
        escalation_reason="Sufficient historical evidence found.",
        evidence=[
            EvidenceItem(
                case_id="c1",
                conversation_id="conv1",
                similarity=0.91,
                customer_message="Battery draining fast",
                historical_response="Check battery health.",
            )
        ],
    )
    assert resp.intent == IntentEnum.BATTERY_CHARGING
    assert resp.intent_confidence == 0.92
    assert not resp.escalate
    assert len(resp.evidence) == 1


def test_health_response_schema():
    """Verify health response serializes properly."""
    health = HealthResponse(
        status="healthy",
        app_name="Hiver Support Agent",
        version="0.1.0",
        environment="testing",
        database=DatabaseHealth(
            status="connected",
            details="Ping OK",
        ),
    )
    data = health.model_dump()
    assert data["database"]["status"] == "connected"
    assert data["status"] == "healthy"
