"""Unit and integration tests for the TF-IDF retrieval system."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app
from src.retriever import TFIDFRetriever, get_retriever
from src.schemas import EvidenceItem

client = TestClient(app)


@pytest.fixture
def sample_cases():
    """Fixture providing a small, controlled corpus of historical cases."""
    return [
        {
            "case_id": "case_battery_1",
            "conversation_id": "conv_battery_1",
            "customer_message": "My iPhone battery is draining extremely fast after updating to iOS 11.",
            "apple_support_response": "We can help. Let's check Battery Health in Settings and restart.",
            "conversation_context": "Apple: Hello\nCust: Battery problem",
        },
        {
            "case_id": "case_icloud_2",
            "conversation_id": "conv_icloud_2",
            "customer_message": "I forgot my Apple ID and iCloud password. How do I reset it?",
            "apple_support_response": "You can reset your Apple ID password by going to iforgot.apple.com.",
            "conversation_context": None,
        },
        {
            "case_id": "case_screen_3",
            "conversation_id": "conv_screen_3",
            "customer_message": "My screen is totally black, touch is unresponsive and frozen.",
            "apple_support_response": "Please perform a forced restart using volume down and power buttons.",
            "conversation_context": None,
        },
    ]


def test_retriever_unfitted_raises():
    """Verify calling retrieve on an unfitted retriever raises RuntimeError."""
    retriever = TFIDFRetriever()
    with pytest.raises(RuntimeError, match="must be fitted"):
        retriever.retrieve("battery dying")


def test_retriever_empty_fit_raises():
    """Verify fitting on empty cases raises ValueError."""
    retriever = TFIDFRetriever()
    with pytest.raises(ValueError, match="empty cases list"):
        retriever.fit([])


def test_tfidf_retrieval_ranking_and_scores(sample_cases):
    """Verify semantic ranking and score boundaries."""
    retriever = TFIDFRetriever()
    retriever.fit(sample_cases)

    # Query 1: Battery issue
    results = retriever.retrieve("My battery dies within two hours on iOS", top_k=2)
    assert len(results) == 2
    assert results[0].case_id == "case_battery_1"
    assert results[0].similarity > 0.1
    assert 0.0 <= results[0].similarity <= 1.0
    assert "Battery Health" in results[0].historical_response

    # Query 2: Password reset
    results_pwd = retriever.retrieve("need to reset password for apple id", top_k=1)
    assert len(results_pwd) == 1
    assert results_pwd[0].case_id == "case_icloud_2"
    assert "iforgot.apple.com" in results_pwd[0].historical_response


def test_retriever_empty_or_whitespace_query(sample_cases):
    """Verify blank or whitespace queries return empty results without error."""
    retriever = TFIDFRetriever()
    retriever.fit(sample_cases)

    assert retriever.retrieve("") == []
    assert retriever.retrieve("   \t\n  ") == []


def test_retriever_save_and_load(sample_cases, tmp_path):
    """Verify that saving and loading produces identical results."""
    retriever = TFIDFRetriever()
    retriever.fit(sample_cases)

    save_path = tmp_path / "test_retriever.joblib"
    retriever.save(save_path)
    assert save_path.exists()

    loaded = TFIDFRetriever.load(save_path)
    assert loaded.is_fitted
    assert len(loaded.cases) == len(sample_cases)

    orig_res = retriever.retrieve("battery drain issue", top_k=2)
    load_res = loaded.retrieve("battery drain issue", top_k=2)

    assert len(orig_res) == len(load_res)
    assert orig_res[0].case_id == load_res[0].case_id
    assert orig_res[0].similarity == load_res[0].similarity


def test_api_retrieve_endpoint():
    """Verify POST /api/v1/retrieve endpoint through FastAPI test client."""
    response = client.post(
        "/api/v1/retrieve",
        json={"message": "My battery drains too fast", "top_k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "My battery drains too fast"
    assert data["top_k"] == 3
    assert "results" in data
    assert len(data["results"]) == 3
    first = data["results"][0]
    assert "case_id" in first
    assert "similarity" in first
    assert "customer_message" in first
    assert "historical_response" in first


def test_api_retrieve_validation_error():
    """Verify 422 validation on empty message or invalid top_k."""
    # Empty message
    resp_empty = client.post("/api/v1/retrieve", json={"message": ""})
    assert resp_empty.status_code == 422

    # Whitespace message
    resp_ws = client.post("/api/v1/retrieve", json={"message": "   "})
    assert resp_ws.status_code == 422

    # top_k out of bounds
    resp_k = client.post("/api/v1/retrieve", json={"message": "Help", "top_k": 50})
    assert resp_k.status_code == 422
