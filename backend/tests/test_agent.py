"""Unit and integration tests for Phase 6 Conversation-Aware Support Decision Engine.

Validates:
1. Clear query auto-handling (e.g. battery drain)
2. Ambiguous query clarification (e.g. 'It stopped working after I updated it.')
3. Multi-turn conversation clarification flow (Wi-Fi issue resolved after clarifying)
4. Repeated unsuccessful troubleshooting detection & escalation
5. Sensitive hardware damage and human representative escalation
6. FastAPI POST /api/v1/agent endpoint integration and validation
7. Preservation of existing /health, /api/v1/classify, and /api/v1/retrieve endpoints
8. Strict verification that data/apple_goldset.csv is never used in decision logic
"""

import ast
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app
from src.agent import SupportDecisionAgent, get_support_agent
from src.conversation import ConversationState
from src.schemas import (
    AgentRequest,
    AgentResponse,
    IntentEnum,
    MessageItem,
    MessageRole,
    SupportAction,
)

client = TestClient(app)
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


# ------------------------------------------------------------------------------
# Test A: Clear Battery Issue -> AUTO_HANDLE
# ------------------------------------------------------------------------------
def test_clear_battery_issue_autohandle():
    """Verify clear, specific battery inquiry with strong evidence leads to AUTO_HANDLE."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_battery_01",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="My iPhone battery is draining very quickly after the latest update.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.AUTO_HANDLE
    assert resp.action != SupportAction.CLARIFY
    assert resp.intent == IntentEnum.BATTERY_CHARGING
    assert resp.intent_confidence > 0.60
    assert not resp.signals.ambiguous
    assert resp.signals.evidence_sufficient
    assert not resp.signals.repeated_troubleshooting
    assert resp.clarification_question is None
    assert len(resp.evidence) > 0


# ------------------------------------------------------------------------------
# Test B: Ambiguous Query -> CLARIFY
# ------------------------------------------------------------------------------
def test_ambiguous_query_clarify():
    """Verify vague pronouns and missing referents trigger CLARIFY with a targeted question."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_ambiguous_01",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="It stopped working after I updated it.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.CLARIFY
    assert resp.action != SupportAction.AUTO_HANDLE
    assert resp.signals.ambiguous is True
    assert not resp.signals.evidence_sufficient
    assert resp.clarification_question is not None
    assert "clarify" in resp.clarification_question.lower()
    # Ensure question mentions possible missing features
    assert any(feat in resp.clarification_question.lower() for feat in ["wi-fi", "app", "messages", "feature"])


# ------------------------------------------------------------------------------
# Test C: Multi-Turn Wi-Fi Clarification Flow
# ------------------------------------------------------------------------------
def test_multiturn_clarification_flow():
    """Verify that after the customer clarifies the missing entity, action ceases to be CLARIFY."""
    agent = get_support_agent()

    # Turn 1 + Turn 2 + Turn 3
    messages = [
        MessageItem(
            role=MessageRole.CUSTOMER,
            text="It stopped working after I updated it.",
        ),
        MessageItem(
            role=MessageRole.ASSISTANT,
            text="Could you clarify what stopped working after the update—for example, Wi-Fi, Messages, an app, or another feature?",
        ),
        MessageItem(
            role=MessageRole.CUSTOMER,
            text="My Wi-Fi won't connect.",
        ),
    ]
    req = AgentRequest(conversation_id="test_clarify_flow_01", messages=messages)
    resp = agent.process(req)

    # After Turn 3, "Wi-Fi" is explicit: must no longer be marked ambiguous
    assert not resp.signals.ambiguous
    assert resp.action != SupportAction.CLARIFY
    assert resp.intent == IntentEnum.CONNECTIVITY
    assert resp.action == SupportAction.AUTO_HANDLE
    assert resp.clarification_question is None


# ------------------------------------------------------------------------------
# Test D: Repeated Failed Troubleshooting -> ESCALATE
# ------------------------------------------------------------------------------
def test_repeated_troubleshooting_escalates():
    """Verify that repeated unsuccessful troubleshooting advice triggers ESCALATE."""
    agent = get_support_agent()

    messages = [
        MessageItem(role=MessageRole.CUSTOMER, text="My Wi-Fi isn't working."),
        MessageItem(role=MessageRole.ASSISTANT, text="Try forgetting the Wi-Fi network and reconnecting."),
        MessageItem(role=MessageRole.CUSTOMER, text="I already tried that."),
        MessageItem(role=MessageRole.ASSISTANT, text="Please restart your router and try again."),
        MessageItem(role=MessageRole.CUSTOMER, text="I already did that too."),
    ]
    req = AgentRequest(conversation_id="test_repeat_troubleshoot_01", messages=messages)
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE
    assert resp.signals.repeated_troubleshooting is True
    assert "troubleshooting" in resp.reason.lower()
    assert resp.clarification_question is None


# ------------------------------------------------------------------------------
# Test E: Sensitive Hardware Damage Escalation
# ------------------------------------------------------------------------------
def test_sensitive_hardware_damage_escalates():
    """Verify that physical hardware hazards trigger immediate escalation."""
    agent = get_support_agent()

    req = AgentRequest(
        conversation_id="test_hardware_dmg",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="I dropped my phone and the screen is severely cracked and glass is shattering everywhere.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE
    assert "hardware" in resp.reason.lower() or "damage" in resp.reason.lower()


def test_explicit_human_agent_request_escalates():
    """Verify customer explicitly requesting human agent triggers immediate escalation."""
    agent = get_support_agent()

    req = AgentRequest(
        conversation_id="test_human_req",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Please connect me to a human representative right now.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE
    assert "human" in resp.reason.lower()


# ------------------------------------------------------------------------------
# Test F: FastAPI POST /api/v1/agent Integration & Validation
# ------------------------------------------------------------------------------
def test_api_agent_endpoint_success():
    """Verify POST /api/v1/agent endpoint handles structured JSON requests."""
    payload = {
        "conversation_id": "api_test_01",
        "messages": [
            {"role": "customer", "text": "My iPhone battery is draining very quickly after the latest update."}
        ],
    }
    response = client.post("/api/v1/agent", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["conversation_id"] == "api_test_01"
    assert data["action"] == "auto_handle"
    assert data["intent"] == "Battery / Charging"
    assert data["intent_confidence"] > 0.60
    assert "retrieval" in data
    assert "signals" in data
    assert data["signals"]["ambiguous"] is False
    assert data["signals"]["evidence_sufficient"] is True


def test_api_agent_endpoint_validation_error():
    """Verify 422 Unprocessable Entity when messages array is empty or lacks customer role."""
    # Empty messages list
    resp_empty = client.post("/api/v1/agent", json={"messages": []})
    assert resp_empty.status_code == 422

    # Assistant-only message without customer turn
    resp_no_cust = client.post(
        "/api/v1/agent",
        json={"messages": [{"role": "assistant", "text": "Hello, how can I help?"}]},
    )
    assert resp_no_cust.status_code == 422

    # Blank customer text
    resp_blank = client.post(
        "/api/v1/agent",
        json={"messages": [{"role": "customer", "text": "   "}]},
    )
    assert resp_blank.status_code == 422


# ------------------------------------------------------------------------------
# Test G: Backward Compatibility of Existing Endpoints
# ------------------------------------------------------------------------------
def test_existing_endpoints_preserved():
    """Ensure /health, /api/v1/classify, and /api/v1/retrieve continue to work."""
    # 1. Health check
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    # 2. Intent classifier endpoint
    classify_resp = client.post("/api/v1/classify", json={"message": "Forgot my iCloud password"})
    assert classify_resp.status_code == 200
    assert "intent" in classify_resp.json()

    # 3. Retrieval endpoint (both semantic and tfidf)
    ret_sem = client.post("/api/v1/retrieve", json={"message": "battery issue", "retriever": "semantic"})
    assert ret_sem.status_code == 200
    assert ret_sem.json()["retriever"] == "semantic"

    ret_tfidf = client.post("/api/v1/retrieve", json={"message": "battery issue", "retriever": "tfidf"})
    assert ret_tfidf.status_code == 200
    assert ret_tfidf.json()["retriever"] == "tfidf"


# ------------------------------------------------------------------------------
# Test H: Golden Set Zero Contamination Verification
# ------------------------------------------------------------------------------
def test_golden_set_never_used_in_decision_logic():
    """Statically inspect Phase 6 source files to verify apple_goldset.csv is never referenced."""
    source_files = [
        BACKEND_DIR / "src" / "conversation.py",
        BACKEND_DIR / "src" / "escalation.py",
        BACKEND_DIR / "src" / "agent.py",
    ]
    for filepath in source_files:
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert "apple_goldset" not in content.lower(), (
            f"Violation: {filepath.name} references apple_goldset!"
        )
        assert "goldset" not in content.lower(), (
            f"Violation: {filepath.name} references goldset!"
        )


# ==============================================================================
# Phase 10: Targeted Agent Improvement Tests
# ==============================================================================


# ------------------------------------------------------------------------------
# Test I: Resolved Conversation -> AUTO_HANDLE (not ESCALATE)
# ------------------------------------------------------------------------------
def test_resolved_conversation_not_escalated():
    """Phase 10: Customer says problem is fixed -> should auto_handle, not escalate."""
    agent = get_support_agent()
    messages = [
        MessageItem(role=MessageRole.CUSTOMER, text="My WiFi isn't working."),
        MessageItem(role=MessageRole.ASSISTANT, text="Try reconnecting to the network."),
        MessageItem(role=MessageRole.CUSTOMER, text="Thank you, it works now."),
    ]
    req = AgentRequest(conversation_id="test_resolved_01", messages=messages)
    resp = agent.process(req)

    assert resp.action != SupportAction.ESCALATE, "Resolved conversation should NOT escalate"
    assert resp.action == SupportAction.AUTO_HANDLE
    assert resp.signals.resolved_closing is True


def test_closing_thank_you_not_escalated():
    """Phase 10: Customer says 'Thanks 😊' -> should auto_handle, not escalate."""
    agent = get_support_agent()
    messages = [
        MessageItem(role=MessageRole.CUSTOMER, text="I need help with my iCloud."),
        MessageItem(role=MessageRole.ASSISTANT, text="Sure, let me help."),
        MessageItem(role=MessageRole.CUSTOMER, text="Managed to get on a call, thanks though 😊"),
    ]
    req = AgentRequest(conversation_id="test_closing_01", messages=messages)
    resp = agent.process(req)

    assert resp.action != SupportAction.ESCALATE, "Closing conversation should NOT escalate"
    assert resp.signals.resolved_closing is True


def test_resolved_sorted_not_escalated():
    """Phase 10: 'It's sorted now' -> auto_handle even with past frustration."""
    agent = get_support_agent()
    messages = [
        MessageItem(role=MessageRole.CUSTOMER, text="It's sorted now. It just cost me a lot of stress."),
    ]
    req = AgentRequest(conversation_id="test_sorted_01", messages=messages)
    resp = agent.process(req)

    assert resp.action != SupportAction.ESCALATE, "Resolved conversation should NOT escalate"
    assert resp.signals.resolved_closing is True


# ------------------------------------------------------------------------------
# Test J: Improved Repeated Troubleshooting Detection (Phase 8A Regressions)
# ------------------------------------------------------------------------------
def test_repeated_troubleshooting_still_having_problems():
    """Phase 10 Regression (Gold #2): 'Still having problems' must trigger escalation."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_gold2_regression",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Last night my keyboard disappeared while trying to text so I reset the phone settings. Still having problems.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE, "Gold #2: 'Still having problems' must escalate"
    assert resp.signals.repeated_troubleshooting is True


def test_repeated_troubleshooting_tried_steps():
    """Phase 10 Regression (Gold #44): 'Tried the steps. Still receiving an error' must escalate."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_gold44_regression",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Tried the steps. Still receiving an error message. Just updated to iOS 11.1.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE, "Gold #44: 'Tried the steps' must escalate"
    assert resp.signals.repeated_troubleshooting is True


def test_repeated_troubleshooting_doesnt_work():
    """Phase 10: 'Doesn't work' with frustrated emoji -> should escalate."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_gold26_regression",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Doesn't work 😣",
            )
        ],
    )
    resp = agent.process(req)

    # Should escalate due to frustration + unresolved, or troubleshooting failure
    assert resp.action == SupportAction.ESCALATE, "Gold #26: 'Doesn't work 😣' must escalate"


# ------------------------------------------------------------------------------
# Test K: Frustration + Unresolved -> ESCALATE (Phase 8A Regressions)
# ------------------------------------------------------------------------------
def test_angry_emoji_escalation():
    """Phase 10 Regression (Gold #6): Angry message with 😡 should escalate."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_gold6_regression",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Yes it's successfully updated to iOS 11.0.2 - also do u really think that customer should DM u or u should try to reach out to customer??? 😡",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE, "Gold #6: Angry 😡 message should escalate"
    assert resp.signals.frustrated is True


def test_frustrated_dm_several_times():
    """Phase 10 Regression (Gold #153): 'dm you several times and still' -> escalate."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_gold153_regression",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="No your not, I have dm you several times and still my battery issues",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.ESCALATE, "Gold #153: Frustrated + repeated DMs must escalate"


# ------------------------------------------------------------------------------
# Test L: Low Confidence -> CLARIFY (not ESCALATE) — Phase 10 Policy Change
# ------------------------------------------------------------------------------
def test_low_confidence_clarifies_not_escalates():
    """Phase 10: Low intent confidence should trigger CLARIFY, not ESCALATE."""
    agent = get_support_agent()
    # A conversational filler message that the classifier struggles with.
    # In Phase 8, Gold #135 "Sometimes it occurs more than once a day" got 0.23 confidence.
    # The key Phase 10 guarantee: low confidence -> CLARIFY, never ESCALATE.
    req = AgentRequest(
        conversation_id="test_low_conf_clarify",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="Sometimes it occurs more than once a day.",
            )
        ],
    )
    resp = agent.process(req)

    # Phase 10 guarantee: low confidence must NOT escalate
    assert resp.action != SupportAction.ESCALATE, "Low confidence should CLARIFY, not ESCALATE"
    # Should be CLARIFY (low confidence or ambiguous)
    assert resp.action == SupportAction.CLARIFY


# ------------------------------------------------------------------------------
# Test M: Ambiguous Referent Still Clarifies (Regression)
# ------------------------------------------------------------------------------
def test_ambiguous_referent_still_clarifies():
    """Phase 10: Verify ambiguous referent behavior is preserved from Phase 6."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_ambiguous_preserved",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="It stopped working after I updated it.",
            )
        ],
    )
    resp = agent.process(req)

    assert resp.action == SupportAction.CLARIFY
    assert resp.signals.ambiguous is True
    assert resp.clarification_question is not None


# ------------------------------------------------------------------------------
# Test N: DecisionSignals includes new Phase 10 fields
# ------------------------------------------------------------------------------
def test_decision_signals_contain_phase10_fields():
    """Phase 10: Verify API response includes frustrated and resolved_closing signals."""
    payload = {
        "conversation_id": "test_signals_fields",
        "messages": [
            {"role": "customer", "text": "My iPhone battery is draining very quickly after the latest update."}
        ],
    }
    response = client.post("/api/v1/agent", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "frustrated" in data["signals"]
    assert "resolved_closing" in data["signals"]
    assert isinstance(data["signals"]["frustrated"], bool)
    assert isinstance(data["signals"]["resolved_closing"], bool)

