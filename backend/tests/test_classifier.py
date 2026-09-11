"""Unit and integration tests for the supervised Intent Classifier."""

import pytest
from fastapi.testclient import TestClient

from main import app
from src.classifier import IntentClassifier, get_classifier
from src.schemas import ClassificationResponse, IntentEnum

client = TestClient(app)


@pytest.fixture
def sample_training_data():
    """Fixture providing minimal balanced multi-class training data."""
    texts = [
        "My battery is draining extremely fast after updating.",
        "Phone battery percentage drops from 80 to 20 in 10 minutes.",
        "How do I reset my Apple ID and iCloud password?",
        "Forgot my Apple ID passcode and cannot log in.",
        "The screen is black, cracked, and completely unresponsive.",
        "Home button and volume rocker are not responding.",
        "Wi-Fi keeps disconnecting every few minutes on my router.",
        "Bluetooth will not connect to my car or headphones.",
        "iMessage is failing to send and showing red exclamation mark.",
        "Phone calls drop immediately after dialing.",
        "Apple Music won't play downloaded songs offline.",
        "iTunes album purchase is missing from my library.",
    ]
    labels = [
        IntentEnum.BATTERY_CHARGING.value,
        IntentEnum.BATTERY_CHARGING.value,
        IntentEnum.APPLE_ID_ACCOUNT.value,
        IntentEnum.APPLE_ID_ACCOUNT.value,
        IntentEnum.DEVICE_HARDWARE.value,
        IntentEnum.DEVICE_HARDWARE.value,
        IntentEnum.CONNECTIVITY.value,
        IntentEnum.CONNECTIVITY.value,
        IntentEnum.MESSAGES_CALLING.value,
        IntentEnum.MESSAGES_CALLING.value,
        IntentEnum.MUSIC_MEDIA.value,
        IntentEnum.MUSIC_MEDIA.value,
    ]
    return texts, labels


def test_classifier_unfitted_raises():
    """Verify predicting on an untrained classifier raises RuntimeError."""
    clf = IntentClassifier()
    with pytest.raises(RuntimeError, match="must be trained"):
        clf.predict("battery dead")


def test_classifier_empty_train_raises():
    """Verify training on empty data raises ValueError."""
    clf = IntentClassifier()
    with pytest.raises(ValueError, match="cannot be empty"):
        clf.train([], [])


def test_classifier_length_mismatch_raises():
    """Verify training with mismatched lengths raises ValueError."""
    clf = IntentClassifier()
    with pytest.raises(ValueError, match="Length mismatch"):
        clf.train(["text1", "text2"], ["label1"])


def test_classifier_training_and_probabilities(sample_training_data):
    """Verify training, prediction, and probability normalization."""
    texts, labels = sample_training_data
    clf = IntentClassifier(max_features=5000)
    metrics = clf.train(texts, labels)

    assert clf.is_trained
    assert "train_accuracy" in metrics
    assert metrics["num_classes"] == 6

    # Test prediction
    pred = clf.predict("My battery is dying quickly")
    assert pred == IntentEnum.BATTERY_CHARGING.value

    # Test probability distribution
    probs = clf.predict_proba("My battery is dying quickly")
    assert isinstance(probs, dict)
    assert len(probs) == 6
    # Probabilities should sum to approximately 1.0
    total_prob = sum(probs.values())
    assert 0.99 <= total_prob <= 1.01
    assert probs[IntentEnum.BATTERY_CHARGING.value] == max(probs.values())
    assert probs[IntentEnum.BATTERY_CHARGING.value] > 0.25


def test_classifier_classify_structured_response(sample_training_data):
    """Verify classify() returns valid Pydantic ClassificationResponse."""
    texts, labels = sample_training_data
    clf = IntentClassifier(max_features=5000)
    clf.train(texts, labels)

    response = clf.classify("Forgot Apple ID password")
    assert isinstance(response, ClassificationResponse)
    assert response.intent == IntentEnum.APPLE_ID_ACCOUNT
    assert 0.0 <= response.confidence <= 1.0
    assert len(response.top_predictions) == 6
    assert response.top_predictions[0].confidence == response.confidence


def test_classifier_save_and_load(sample_training_data, tmp_path):
    """Verify saving and loading produces identical predictions."""
    texts, labels = sample_training_data
    clf = IntentClassifier(max_features=5000)
    clf.train(texts, labels)

    save_file = tmp_path / "test_classifier.joblib"
    clf.save(save_file)
    assert save_file.exists()

    loaded = IntentClassifier.load(save_file)
    assert loaded.is_trained
    assert loaded.classes == clf.classes

    q = "My screen is cracked and black"
    assert clf.predict(q) == loaded.predict(q)
    assert clf.predict_proba(q) == loaded.predict_proba(q)


def test_api_classify_endpoint():
    """Verify POST /api/v1/classify integration via TestClient."""
    response = client.post(
        "/api/v1/classify",
        json={"message": "My iPhone battery dies so fast after iOS 11 update"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "intent" in data
    assert "confidence" in data
    assert "top_predictions" in data
    assert len(data["top_predictions"]) >= 1
    # Battery / Charging or iOS / Software
    assert data["intent"] in [IntentEnum.BATTERY_CHARGING.value, IntentEnum.IOS_SOFTWARE.value]
    assert 0.0 <= data["confidence"] <= 1.0


def test_api_classify_validation_error():
    """Verify validation error on empty or whitespace message."""
    resp_empty = client.post("/api/v1/classify", json={"message": ""})
    assert resp_empty.status_code == 422

    resp_ws = client.post("/api/v1/classify", json={"message": "   \n\t "})
    assert resp_ws.status_code == 422


def test_all_12_canonical_intents_exist():
    """Verify all 12 canonical intent strings are exactly defined in Intent."""
    from src.schemas import Intent

    canonical_strings = {
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
    actual_strings = {i.value for i in Intent}
    assert actual_strings == canonical_strings
    assert len(Intent) == 12


def test_golden_set_leakage_isolation():
    """Automated assertion: Golden Set conversation IDs do not enter training data."""
    import json
    from pathlib import Path
    import pandas as pd

    golden_path = Path(__file__).resolve().parent.parent.parent / "data" / "apple_goldset.csv"
    cases_path = Path(__file__).resolve().parent.parent.parent / "data" / "prepared_cases.jsonl"

    assert golden_path.exists(), f"Canonical Golden Set missing at {golden_path}"
    assert cases_path.exists(), f"Prepared cases missing at {cases_path}"

    df_gold = pd.read_csv(golden_path)
    golden_conv_ids = set(df_gold["conversation_id"].dropna().astype(str).str.strip().unique())
    assert len(golden_conv_ids) == 200, f"Expected 200 Golden Set conversations, found {len(golden_conv_ids)}"

    with open(cases_path, "r", encoding="utf-8") as f:
        training_conv_ids = {json.loads(line)["conversation_id"] for line in f if line.strip()}

    training_golden_overlap = training_conv_ids.intersection(golden_conv_ids)
    # Strict automated assertion
    assert len(training_golden_overlap) == 0, (
        f"Leakage detected! {len(training_golden_overlap)} Golden Set conversation IDs found in training data: {training_golden_overlap}"
    )


def test_classifier_output_uses_canonical_intent_strings():
    """Verify classifier predictions only use strings from the canonical intent taxonomy."""
    from src.schemas import Intent

    clf = get_classifier()
    if clf and clf.is_trained:
        canonical_values = {i.value for i in Intent}
        # Check all internal classes
        for cls_name in clf.classes:
            assert cls_name in canonical_values, f"Non-canonical class name found: {cls_name}"

        # Test classify output
        res = clf.classify("My iPhone battery dies too quickly")
        assert res.intent.value in canonical_values
        for item in res.top_predictions:
            assert item.intent.value in canonical_values
            assert 0.0 <= item.confidence <= 1.0
