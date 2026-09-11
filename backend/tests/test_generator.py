"""Unit and integration tests for Phase 7 Grounded LLM Response Generation.

Validates:
1. AUTO_HANDLE generation grounded in retrieved historical evidence.
2. CLARIFY generation producing targeted clarification questions without troubleshooting.
3. ESCALATE generation producing empathetic handoff messages without repeating failed steps.
4. Robust fallback handling on OpenRouter timeout, rate-limit, and connection errors.
5. Deterministic fallback behavior when no API key is provided.
6. End-to-end integration through SupportDecisionAgent and FastAPI endpoint.
7. Strict Golden Set non-contamination verification.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from src.agent import SupportDecisionAgent, get_support_agent
from src.config import Settings
from src.conversation import ConversationState
from src.generator import (
    SupportResponseGenerator,
    get_fallback_auto_handle,
    get_fallback_clarify,
    get_fallback_escalate,
    get_response_generator,
)
from src.schemas import (
    AgentRequest,
    AgentResponse,
    EvidenceItem,
    IntentEnum,
    MessageItem,
    MessageRole,
    SupportAction,
)

client = TestClient(app)
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


# ------------------------------------------------------------------------------
# Fixtures & Helpers
# ------------------------------------------------------------------------------

def make_mock_openai_response(content: str):
    """Helper to create an OpenAI ChatCompletion mock object."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


@pytest.fixture
def sample_evidence():
    """Sample retrieved historical evidence."""
    return [
        EvidenceItem(
            case_id="case_101",
            conversation_id="conv_101",
            similarity=0.8825,
            customer_message="My iPhone battery drains within two hours after updating to the new iOS version.",
            historical_response="We can help look into your battery. Check Settings > Battery > Battery Health to check maximum capacity.",
        ),
        EvidenceItem(
            case_id="case_102",
            conversation_id="conv_102",
            similarity=0.7950,
            customer_message="Battery dies very fast since the update.",
            historical_response="Let's make sure apps aren't using background activity under Settings > Battery.",
        ),
    ]


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    mock_client = MagicMock()
    return mock_client


# ------------------------------------------------------------------------------
# Test 1: AUTO_HANDLE Grounded Generation
# ------------------------------------------------------------------------------
def test_generator_auto_handle_mock(sample_evidence, mock_openai_client):
    """Verify AUTO_HANDLE sends prompt grounded in evidence and returns generated text."""
    expected_reply = (
        "Battery drain after an update can be frustrating. Let's check Settings > Battery "
        "to see which apps are consuming power and inspect your Battery Health."
    )
    mock_openai_client.chat.completions.create.return_value = make_mock_openai_response(expected_reply)

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_mock_key"),
        client=mock_openai_client,
    )

    conv = ConversationState(
        conversation_id="conv_auto_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="My battery is draining quickly after the update.")
        ],
    )

    response_text, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.BATTERY_CHARGING,
        evidence=sample_evidence,
        decision_reason="Confident intent and sufficient retrieval evidence.",
    )

    assert not is_fallback
    assert response_text == expected_reply
    assert mock_openai_client.chat.completions.create.called

    call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    sys_content = messages[0]["content"]
    user_content = messages[1]["content"]

    # Verify system prompt enforces grounding rules
    assert "Apple customer-support" in sys_content
    assert "historical AppleSupport interactions" in sys_content
    assert "NEVER invent or hallucinate" in sys_content

    # Verify user prompt includes evidence and intent
    assert "BATTERY_CHARGING" in user_content or "Battery / Charging" in user_content
    assert "Settings > Battery" in user_content


# ------------------------------------------------------------------------------
# Test 2: CLARIFY Generation (Targeted question, no troubleshooting)
# ------------------------------------------------------------------------------
def test_generator_clarify_mock(mock_openai_client):
    """Verify CLARIFY generates a question without troubleshooting."""
    expected_question = (
        "Could you clarify what stopped working after the update—for example, Wi-Fi, "
        "Messages, an app, or another feature?"
    )
    mock_openai_client.chat.completions.create.return_value = make_mock_openai_response(expected_question)

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_mock_key"),
        client=mock_openai_client,
    )

    conv = ConversationState(
        conversation_id="conv_clarify_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="It stopped working after I updated it.")
        ],
    )

    response_text, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.CLARIFY,
        intent=IntentEnum.IOS_SOFTWARE,
        evidence=[],
        clarification_question="Could you clarify what stopped working after the update?",
        decision_reason="Customer query is ambiguous or missing specific device/feature context.",
    )

    assert not is_fallback
    assert response_text == expected_question

    call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
    sys_content = call_kwargs["messages"][0]["content"]
    assert "Do NOT guess" in sys_content
    assert "Do NOT provide troubleshooting steps" in sys_content


# ------------------------------------------------------------------------------
# Test 3: ESCALATE Generation (Empathetic handoff, no repeated steps)
# ------------------------------------------------------------------------------
def test_generator_escalate_mock(mock_openai_client):
    """Verify ESCALATE generates an empathetic handoff message without repeating steps."""
    expected_handoff = (
        "I’m sorry to hear that restarting and resetting network settings haven’t resolved "
        "the Wi-Fi issue. I recommend connecting with an Apple Support specialist who can investigate further."
    )
    mock_openai_client.chat.completions.create.return_value = make_mock_openai_response(expected_handoff)

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_mock_key"),
        client=mock_openai_client,
    )

    conv = ConversationState(
        conversation_id="conv_esc_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="My Wi-Fi is broken."),
            MessageItem(role=MessageRole.ASSISTANT, text="Have you tried resetting network settings?"),
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="I already tried resetting network settings and restarted, it still won't connect.",
            ),
        ],
    )

    response_text, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.ESCALATE,
        intent=IntentEnum.CONNECTIVITY,
        evidence=[],
        decision_reason="Previous troubleshooting attempts have failed.",
    )

    assert not is_fallback
    assert response_text == expected_handoff

    call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
    sys_content = call_kwargs["messages"][0]["content"]
    assert "Do NOT repeat or suggest the troubleshooting steps that have already failed" in sys_content


# ------------------------------------------------------------------------------
# Test 4: Robust Failure Handling & Deterministic Fallbacks
# ------------------------------------------------------------------------------
def test_generator_fallback_on_api_error(sample_evidence):
    """Verify that when OpenRouter client raises an exception, safe fallback is returned without crashing."""
    mock_failing_client = MagicMock()
    mock_failing_client.chat.completions.create.side_effect = RuntimeError("OpenRouter API timed out or unreachable")

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_key"),
        client=mock_failing_client,
    )

    conv = ConversationState(
        conversation_id="conv_fail_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="My battery is draining.")
        ],
    )

    # auto_handle fallback
    resp_auto, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.BATTERY_CHARGING,
        evidence=sample_evidence,
    )
    assert is_fallback is True
    assert "Battery" in resp_auto
    assert len(resp_auto) > 20

    # clarify fallback
    resp_clarify, is_fallback_clarify = generator.generate(
        conversation=conv,
        action=SupportAction.CLARIFY,
        intent=IntentEnum.OTHER_GENERAL,
        evidence=[],
        clarification_question="Could you clarify which app crashed?",
    )
    assert is_fallback_clarify is True
    assert "Could you clarify which app crashed?" in resp_clarify

    # escalate fallback
    resp_esc, is_fallback_esc = generator.generate(
        conversation=conv,
        action=SupportAction.ESCALATE,
        intent=IntentEnum.CONNECTIVITY,
        evidence=[],
    )
    assert is_fallback_esc is True
    assert "Apple Support specialist" in resp_esc


def test_generator_no_api_key_deterministic_fallback(sample_evidence):
    """Verify that when no API key is provided, generator uses deterministic fallbacks immediately."""
    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY=None),
        client=None,
    )

    conv = ConversationState(
        conversation_id="conv_nokey_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="My screen is black.")
        ],
    )

    resp, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.DEVICE_HARDWARE,
        evidence=sample_evidence,
    )

    assert is_fallback is True
    assert isinstance(resp, str)
    assert len(resp) > 10


def test_generator_empty_completion_fallback(sample_evidence):
    """Verify that an empty completion from LLM triggers fallback."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = make_mock_openai_response("   ")

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_key"),
        client=mock_client,
    )

    conv = ConversationState(
        conversation_id="conv_empty_01",
        messages=[
            MessageItem(role=MessageRole.CUSTOMER, text="Help with my battery.")
        ],
    )

    resp, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.BATTERY_CHARGING,
        evidence=sample_evidence,
    )

    assert is_fallback is True
    assert len(resp) > 10


# ------------------------------------------------------------------------------
# Test 5: End-to-End SupportDecisionAgent with Generator
# ------------------------------------------------------------------------------
def test_agent_with_generator_end_to_end():
    """Verify that SupportDecisionAgent executes full pipeline and populates response field."""
    agent = get_support_agent()
    req = AgentRequest(
        conversation_id="test_agent_gen_01",
        messages=[
            MessageItem(
                role=MessageRole.CUSTOMER,
                text="My iPhone battery is draining very quickly after the latest update.",
            )
        ],
    )
    resp = agent.process(req)

    assert isinstance(resp, AgentResponse)
    assert resp.action == SupportAction.AUTO_HANDLE
    assert resp.response is not None
    assert isinstance(resp.response, str)
    assert len(resp.response.strip()) > 0
    # No internal system metrics leaked in response
    assert "0." not in resp.response
    assert "case_" not in resp.response.lower()
    assert "similarity" not in resp.response.lower()


# ------------------------------------------------------------------------------
# Test 6: API POST /api/v1/agent Returns response Field
# ------------------------------------------------------------------------------
def test_api_agent_endpoint_returns_response_field():
    """Verify POST /api/v1/agent returns structured response with response field."""
    payload = {
        "conversation_id": "test_api_gen_01",
        "messages": [
            {"role": "customer", "text": "It stopped working after I updated it."}
        ],
    }
    res = client.post("/api/v1/agent", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["action"] == "clarify"
    assert "response" in data
    assert len(data["response"]) > 0
    assert "clarification_question" in data
    assert data["clarification_question"] is not None


# ------------------------------------------------------------------------------
# Test 7: Grounding Hardening (No unsupported instructions or fabricated URLs)
# ------------------------------------------------------------------------------
def test_grounding_hardened_rejects_unsupported_actions_and_urls(mock_openai_client):
    """Verify strict prompt grounding and post-generation stripping of raw URLs and handles."""
    # LLM output contains a raw t.co link and Twitter handle from old dataset tweet
    raw_llm_reply = (
        "@Customer123 We can help. Check your current iOS version under General > About. "
        "Visit https://t.co/abc123xyz for more details."
    )
    mock_openai_client.chat.completions.create.return_value = make_mock_openai_response(raw_llm_reply)

    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY="test_key"),
        client=mock_openai_client,
    )

    evidence = [
        EvidenceItem(
            case_id="case_version_check",
            conversation_id="conv_v1",
            similarity=0.82,
            customer_message="What iOS version do I have?",
            historical_response="Check General > About to see your iOS version.",
        )
    ]

    conv = ConversationState(
        conversation_id="conv_grounding_01",
        messages=[MessageItem(role=MessageRole.CUSTOMER, text="What iOS version do I have?")],
    )

    resp_text, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.IOS_SOFTWARE,
        evidence=evidence,
    )

    assert not is_fallback
    # 1. Supported action is preserved
    assert "General > About" in resp_text
    # 2. Raw Twitter handles and URLs are stripped
    assert "https://t.co" not in resp_text
    assert "@Customer123" not in resp_text
    # 3. Prompt verified to contain strict evidence boundary
    call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
    sys_prompt = call_kwargs["messages"][0]["content"]
    user_prompt = call_kwargs["messages"][1]["content"]
    assert "STRICT EVIDENCE BOUNDARY" in sys_prompt
    assert "Do not supplement the evidence with general model knowledge" in sys_prompt
    assert "GROUNDING INSTRUCTION: Base your guidance strictly on the evidence above" in user_prompt


def test_grounding_fallback_does_not_invent_steps_without_evidence():
    """Verify fallback auto_handle does NOT fabricate unmentioned restarts or resets when evidence is empty."""
    generator = SupportResponseGenerator(
        settings=Settings(OPENROUTER_API_KEY=None),
        client=None,
    )

    conv = ConversationState(
        conversation_id="conv_no_step_01",
        messages=[MessageItem(role=MessageRole.CUSTOMER, text="Help with my app.")],
    )

    resp_text, is_fallback = generator.generate(
        conversation=conv,
        action=SupportAction.AUTO_HANDLE,
        intent=IntentEnum.APP_ISSUE,
        evidence=[],
    )

    assert is_fallback is True
    # Must NOT inject unmentioned steps like restarting or network resets
    assert "restarting" not in resp_text.lower()
    assert "network settings" not in resp_text.lower()
    assert "restore" not in resp_text.lower()


# ------------------------------------------------------------------------------
# Test 8: Golden Set Strict Non-Contamination Verification
# ------------------------------------------------------------------------------
def test_golden_set_not_contaminated_phase7():
    """Statically verify that generator.py never references or imports the golden evaluation set."""
    generator_file = BACKEND_DIR / "src" / "generator.py"
    assert generator_file.exists(), f"File {generator_file} must exist"
    content = generator_file.read_text(encoding="utf-8").lower()
    assert "apple_goldset" not in content, "generator.py must not reference golden set"
    assert "goldset" not in content, "generator.py must not reference golden set"
