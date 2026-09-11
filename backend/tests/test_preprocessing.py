"""Unit tests for preprocessing and support case extraction pipeline."""

import pandas as pd
import pytest

from src.preprocessing import clean_text, extract_support_cases, load_golden_set_conversation_ids


def test_clean_text_html_entities_and_whitespace():
    """Verify HTML entities and excessive whitespace are cleaned."""
    raw = "  iPhone &gt; Settings &amp; General \n\n  Check   now.  "
    cleaned = clean_text(raw, strip_leading_handles=False)
    assert cleaned == "iPhone > Settings & General Check now."


def test_clean_text_strip_leading_handles():
    """Verify leading Twitter handles are removed when configured."""
    raw = "@AppleSupport @115854 My battery is draining very fast!"
    cleaned = clean_text(raw, strip_leading_handles=True)
    assert cleaned == "My battery is draining very fast!"


def test_clean_text_handles_none_and_empty():
    """Verify safe fallback for None and non-string inputs."""
    assert clean_text(None) == ""
    assert clean_text("") == ""
    assert clean_text("   ") == ""


def test_extract_support_cases_basic():
    """Verify basic customer -> AppleSupport extraction and pairing."""
    data = {
        "conversation_id": ["conv_1", "conv_1", "conv_1"],
        "message_number": [1, 2, 3],
        "tweet_id": ["101", "102", "103"],
        "speaker": ["AppleSupport", "Customer", "AppleSupport"],
        "text": [
            "We are here to help.",
            "@AppleSupport My screen is completely frozen on iOS 11.",
            "@Customer Try force restarting your device with volume buttons.",
        ],
        "created_at": ["2017-10-01", "2017-10-01", "2017-10-01"],
    }
    df = pd.DataFrame(data)
    cases = extract_support_cases(df)

    assert len(cases) == 1
    case = cases[0]
    assert case.conversation_id == "conv_1"
    assert case.customer_message == "My screen is completely frozen on iOS 11."
    assert "force restarting" in case.apple_support_response
    assert case.conversation_context is not None
    assert "AppleSupport: We are here to help." in case.conversation_context


def test_extract_support_cases_leakage_exclusion():
    """Verify Golden Set conversation IDs are strictly excluded."""
    data = {
        "conversation_id": ["conv_keep", "conv_keep", "conv_leak", "conv_leak"],
        "message_number": [1, 2, 1, 2],
        "tweet_id": ["1", "2", "3", "4"],
        "speaker": ["Customer", "AppleSupport", "Customer", "AppleSupport"],
        "text": [
            "I need help with battery",
            "Please check battery health in settings",
            "This is a golden set conversation",
            "Golden set response",
        ],
        "created_at": ["2017-10-01"] * 4,
    }
    df = pd.DataFrame(data)
    cases = extract_support_cases(df, exclude_conversation_ids={"conv_leak"})

    assert len(cases) == 1
    assert cases[0].conversation_id == "conv_keep"
    assert all(c.conversation_id != "conv_leak" for c in cases)


def test_extract_support_cases_missing_columns_raises():
    """Verify error is raised when required columns are absent."""
    df = pd.DataFrame({"some_col": [1, 2, 3]})
    with pytest.raises(ValueError, match="missing required columns"):
        extract_support_cases(df)
