"""Unit and Integration Tests for Phase 8 Evaluation Harness.

Verifies:
1. Golden Set schema integrity, row count, and strict validation error cases.
2. Conversation reconstruction from dialogue context.
3. Intent classification metrics (accuracy, macro/weighted F1, zero-support classes, 12x12 confusion matrix).
4. Decision & safety metrics (escalation detection, unsafe auto-handle rate, 3-way distribution).
5. Majority class and Simple TF-IDF baselines.
6. Evaluation artifact generation and file structures.
7. Zero Golden Set leakage verification.
"""

from pathlib import Path
import tempfile
import pandas as pd
import pytest

from evaluation.baselines import MajorityClassBaseline, SimpleTFIDFBaseline
from evaluation.golden_set import (
    AUTHORITATIVE_INTENTS,
    REQUIRED_COLUMNS,
    load_and_validate_golden_set,
    reconstruct_conversation,
)
from evaluation.metrics import calculate_decision_metrics, calculate_intent_metrics
from evaluation.report import save_evaluation_artifacts
from src.schemas import MessageItem, MessageRole

GOLDSET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "apple_goldset.csv"
TRAIN_CASES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prepared_cases.jsonl"


# ==============================================================================
# 1. Golden Set Validation Tests
# ==============================================================================

def test_golden_set_valid():
    """Verify that canonical apple_goldset.csv passes all validation checks."""
    assert GOLDSET_PATH.exists(), f"Golden set missing at {GOLDSET_PATH}"
    df = load_and_validate_golden_set(GOLDSET_PATH)

    assert len(df) == 200
    assert df["conversation_id"].nunique() == 200
    assert df["gold_id"].nunique() == 200
    for col in REQUIRED_COLUMNS:
        assert col in df.columns
        assert not df[col].isna().any()

    # All human intents are in the 12 authoritative intents
    assert set(df["human_intent"]).issubset(set(AUTHORITATIVE_INTENTS))

    # All escalation labels are YES or NO
    assert set(df["human_escalate"]).issubset({"YES", "NO"})


def test_golden_set_missing_file():
    """Verify FileNotFoundError is raised if Golden Set does not exist."""
    with pytest.raises(FileNotFoundError):
        load_and_validate_golden_set(Path("non_existent_file.csv"))


def test_golden_set_invalid_row_count(tmp_path):
    """Verify ValueError is raised if row count != 200."""
    bad_df = pd.DataFrame({
        "gold_id": [1, 2],
        "conversation_id": ["conv_1", "conv_2"],
        "conversation_context": ["a", "b"],
        "first_customer_message": ["a", "b"],
        "latest_customer_message": ["a", "b"],
        "human_intent": ["iOS / Software", "iOS / Software"],
        "human_escalate": ["NO", "NO"],
    })
    bad_csv = tmp_path / "bad_count.csv"
    bad_df.to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="exactly 200 rows"):
        load_and_validate_golden_set(bad_csv)


def test_golden_set_missing_columns(tmp_path):
    """Verify ValueError if required columns are missing."""
    rows = []
    for i in range(200):
        rows.append({"gold_id": i + 1, "conversation_id": f"conv_{i+1}"})
    bad_df = pd.DataFrame(rows)
    bad_csv = tmp_path / "missing_cols.csv"
    bad_df.to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        load_and_validate_golden_set(bad_csv)


def test_golden_set_duplicate_ids(tmp_path):
    """Verify ValueError if duplicate conversation_id exists."""
    df = pd.read_csv(GOLDSET_PATH)
    df.loc[1, "conversation_id"] = df.loc[0, "conversation_id"]
    dup_csv = tmp_path / "dup_conv.csv"
    df.to_csv(dup_csv, index=False)

    with pytest.raises(ValueError, match="Duplicate 'conversation_id'"):
        load_and_validate_golden_set(dup_csv)


def test_golden_set_invalid_intent(tmp_path):
    """Verify ValueError if an unapproved intent is present."""
    df = pd.read_csv(GOLDSET_PATH)
    df.loc[0, "human_intent"] = "Invalid_Made_Up_Intent"
    bad_csv = tmp_path / "bad_intent.csv"
    df.to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="invalid intent values"):
        load_and_validate_golden_set(bad_csv)


def test_golden_set_invalid_escalate(tmp_path):
    """Verify ValueError if human_escalate is not YES or NO."""
    df = pd.read_csv(GOLDSET_PATH)
    df.loc[0, "human_escalate"] = "MAYBE"
    bad_csv = tmp_path / "bad_esc.csv"
    df.to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="invalid human_escalate values"):
        load_and_validate_golden_set(bad_csv)


# ==============================================================================
# 2. Conversation Reconstruction Tests
# ==============================================================================

def test_reconstruct_conversation_multi_turn():
    """Verify multi-turn dialogue is parsed into customer and assistant MessageItems."""
    row = pd.Series({
        "conversation_context": (
            "Customer: My iPhone won't turn on.\n"
            "AppleSupport: We can help. Which model do you have?\n"
            "Customer: It is an iPhone 11."
        ),
        "latest_customer_message": "It is an iPhone 11.",
        "first_customer_message": "My iPhone won't turn on.",
    })
    turns = reconstruct_conversation(row)
    assert len(turns) == 3
    assert turns[0].role == MessageRole.CUSTOMER
    assert "won't turn on" in turns[0].text
    assert turns[1].role == MessageRole.ASSISTANT
    assert "Which model" in turns[1].text
    assert turns[2].role == MessageRole.CUSTOMER
    assert "iPhone 11" in turns[2].text


def test_reconstruct_conversation_fallback():
    """Verify fallback to message fields when context has no customer turns."""
    row = pd.Series({
        "conversation_context": "AppleSupport: Thank you for contacting us.",
        "latest_customer_message": "My battery drains quickly.",
        "first_customer_message": "My battery drains quickly.",
    })
    turns = reconstruct_conversation(row)
    assert any(t.role == MessageRole.CUSTOMER for t in turns)
    cust_turn = [t for t in turns if t.role == MessageRole.CUSTOMER][0]
    assert cust_turn.text == "My battery drains quickly."


# ==============================================================================
# 3. Intent Metrics Tests
# ==============================================================================

def test_intent_metrics_calculation():
    """Verify accuracy, macro F1, per-intent breakdown, and zero-support classes."""
    y_true = [
        "iOS / Software",
        "iOS / Software",
        "Battery / Charging",
        "Other / General",
    ]
    y_pred = [
        "iOS / Software",
        "Battery / Charging",
        "Battery / Charging",
        "Other / General",
    ]

    metrics = calculate_intent_metrics(y_true, y_pred)
    assert metrics["accuracy"] == 0.75
    assert metrics["total_evaluated"] == 4
    assert "zero_support_classes" in metrics
    # 9 classes have 0 support in this tiny set
    assert len(metrics["zero_support_classes"]) == 9
    assert "App Store / Purchases" in metrics["zero_support_classes"]

    # Per-intent metrics exist for all 12 intents
    per_intent = metrics["per_intent"]
    assert len(per_intent) == 12

    # Confusion matrix is 12x12
    cm = metrics["confusion_matrix"]
    assert cm.shape == (12, 12)
    assert list(cm.columns) == AUTHORITATIVE_INTENTS
    assert list(cm.index) == AUTHORITATIVE_INTENTS


# ==============================================================================
# 4. Decision and Safety Metrics Tests
# ==============================================================================

def test_decision_metrics_calculation():
    """Verify safety calculation, escalation detection, and 3-way distribution."""
    human_escalate = ["NO", "NO", "YES", "YES", "NO"]
    predicted_actions = ["auto_handle", "clarify", "escalate", "auto_handle", "auto_handle"]

    # Breakdown:
    # 1. auto_handle: 3 items (Indices 0 [NO], 3 [YES], 4 [NO])
    #    safe_autohandle: 2 (Index 0, 4)
    #    unsafe_autohandle: 1 (Index 3: auto_handle + human YES)
    #    autohandle_precision_wrt_no = 2 / 3 = 0.6667
    #    unsafe_autohandle_rate = 1 / 3 = 0.3333
    # 2. clarify: 1 item (Index 1) -> NOT conflated with escalate!
    # 3. escalate: 1 item (Index 2 [YES])
    #    Escalation detection: TP=1, FP=0, FN=1 (Index 3), TN=3. Precision=1.0, Recall=0.5, F1=0.6667

    metrics = calculate_decision_metrics(human_escalate, predicted_actions)

    dist = metrics["action_distribution"]
    assert dist["auto_handle"]["count"] == 3
    assert dist["clarify"]["count"] == 1
    assert dist["escalate"]["count"] == 1

    esc_det = metrics["escalation_detection"]
    assert esc_det["precision"] == 1.0
    assert esc_det["recall"] == 0.5
    assert esc_det["confusion_matrix"]["tp"] == 1
    assert esc_det["confusion_matrix"]["fn"] == 1

    safety = metrics["autohandle_safety"]
    assert safety["total_autohandled"] == 3
    assert safety["safe_autohandled"] == 2
    assert safety["unsafe_autohandled"] == 1
    assert round(safety["autohandle_precision_wrt_no"], 4) == 0.6667
    assert round(safety["unsafe_autohandle_rate"], 4) == 0.3333


def test_decision_metrics_zero_autohandle():
    """Verify graceful handling when total_autohandled is 0."""
    human_escalate = ["YES", "YES"]
    predicted_actions = ["escalate", "clarify"]

    metrics = calculate_decision_metrics(human_escalate, predicted_actions)
    safety = metrics["autohandle_safety"]
    assert safety["total_autohandled"] == 0
    assert safety["autohandle_precision_wrt_no"] == 0.0
    assert safety["unsafe_autohandle_rate"] == 0.0


# ==============================================================================
# 5. Baselines Tests
# ==============================================================================

def test_majority_class_baseline():
    """Verify MajorityClassBaseline always returns 'Other / General'."""
    baseline = MajorityClassBaseline()
    preds = baseline.predict(["My screen is broken", "Battery drained"])
    assert preds == ["Other / General", "Other / General"]
    assert baseline.predict_one("Hello") == "Other / General"


def test_simple_tfidf_baseline():
    """Verify SimpleTFIDFBaseline can predict an authoritative intent."""
    baseline = SimpleTFIDFBaseline()
    baseline.load_or_train()
    pred = baseline.predict_one("My battery drains in 2 hours on my iPhone")
    assert pred in AUTHORITATIVE_INTENTS


# ==============================================================================
# 6. Artifact Generator Test
# ==============================================================================

def test_save_evaluation_artifacts(tmp_path):
    """Verify that all 5 artifact files are written to disk."""
    summary = {
        "dataset": {"total_examples": 200},
        "agent_intent_metrics": {
            "accuracy": 0.85,
            "confusion_matrix": pd.DataFrame([[1, 0], [0, 1]]),
        },
    }
    per_example = [{"gold_id": 1, "predicted_intent": "iOS / Software"}]
    intent_table = [{"intent": "iOS / Software", "f1": 0.88}]
    cm_df = pd.DataFrame([[1, 0], [0, 1]])
    baseline_df = pd.DataFrame([{"Model": "Agent", "Accuracy": 0.85}])

    saved = save_evaluation_artifacts(
        evaluation_summary=summary,
        per_example_rows=per_example,
        intent_metrics_table=intent_table,
        confusion_matrix_df=cm_df,
        baseline_comparison_df=baseline_df,
        output_dir=tmp_path,
    )

    assert len(saved) == 5
    for key, p in saved.items():
        assert p.exists()


# ==============================================================================
# 7. Strict Golden Set Non-Leakage Check
# ==============================================================================

def test_zero_golden_set_leakage():
    """Verify that zero Golden Set conversation IDs exist in prepared_cases.jsonl."""
    assert GOLDSET_PATH.exists()
    assert TRAIN_CASES_PATH.exists()

    df_gold = pd.read_csv(GOLDSET_PATH)
    golden_ids = set(df_gold["conversation_id"])
    assert len(golden_ids) == 200

    import json
    train_ids = set()
    with open(TRAIN_CASES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                train_ids.add(item["conversation_id"])

    overlap = golden_ids.intersection(train_ids)
    assert len(overlap) == 0, f"Critical Leakage: {len(overlap)} Golden Set IDs in training set!"
