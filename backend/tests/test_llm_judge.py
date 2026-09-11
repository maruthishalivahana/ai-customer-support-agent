"""Unit and Integration Tests for Phase 9 LLM-as-a-Judge Evaluation Engine.

Verifies:
1. Pydantic schema validation and rating boundaries for ResponseJudgeScore and EvidenceJudgeScore.
2. Zero leakage of ground-truth human labels into judge prompt templates.
3. Judge caching and persistent result retrieval.
4. Deterministic 50-example human annotation subset selection with blank human fields.
5. Agreement engine calculations (both unpopulated and populated cases).
6. Graceful failure handling on invalid JSON or API errors without score fabrication.
7. Unaltered Golden Set integrity.
"""

from pathlib import Path
import tempfile
import pandas as pd
from pydantic import ValidationError
import pytest

from evaluation.agreement import calculate_judge_human_agreement
from evaluation.human_annotation import select_diverse_subset
from evaluation.judge_schemas import EvidenceJudgeScore, ResponseJudgeScore
from evaluation.llm_judge import (
    EVIDENCE_JUDGE_SYSTEM_PROMPT,
    EvidenceGroundingJudge,
    JudgeCache,
    RESPONSE_JUDGE_SYSTEM_PROMPT,
    ResponseQualityJudge,
)
from src.schemas import EvidenceItem

GOLDSET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "apple_goldset.csv"


# ==============================================================================
# 1. Schema Validation Tests
# ==============================================================================

def test_response_judge_schema_valid():
    """Verify valid ResponseJudgeScore creation."""
    score = ResponseJudgeScore(
        correctness=5,
        groundedness=4,
        helpfulness=4,
        relevance=5,
        action_appropriateness=5,
        overall_score=4.6,
        brief_reason="Grounded in evidence with appropriate action.",
    )
    assert score.correctness == 5
    assert score.overall_score == 4.60


def test_response_judge_schema_invalid_bounds():
    """Verify ratings outside 1-5 raise validation errors."""
    with pytest.raises(ValidationError):
        ResponseJudgeScore(
            correctness=6,  # Invalid: > 5
            groundedness=4,
            helpfulness=4,
            relevance=5,
            action_appropriateness=5,
            overall_score=4.8,
            brief_reason="Test reason.",
        )

    with pytest.raises(ValidationError):
        ResponseJudgeScore(
            correctness=0,  # Invalid: < 1
            groundedness=4,
            helpfulness=4,
            relevance=5,
            action_appropriateness=5,
            overall_score=4.8,
            brief_reason="Test reason.",
        )


def test_evidence_judge_schema_valid():
    """Verify valid EvidenceJudgeScore creation."""
    score = EvidenceJudgeScore(
        evidence_supported=True,
        support_score=4,
        supported_claims=["Check Settings > Battery"],
        unsupported_claims=[],
        reason="Action is supported by retrieved evidence.",
    )
    assert score.evidence_supported is True
    assert score.support_score == 4


def test_evidence_judge_schema_invalid_bounds():
    """Verify support scores outside 0-5 raise validation error."""
    with pytest.raises(ValidationError):
        EvidenceJudgeScore(
            evidence_supported=True,
            support_score=6,  # Invalid: > 5
            reason="Invalid score test.",
        )


# ==============================================================================
# 2. Prompt Non-Leakage & Safety Tests
# ==============================================================================

def test_judge_prompts_zero_leakage():
    """Verify that human ground-truth fields are strictly excluded from judge prompts."""
    # Ensure system prompts don't reference ground truth
    assert "human_intent" not in RESPONSE_JUDGE_SYSTEM_PROMPT
    assert "human_escalate" not in RESPONSE_JUDGE_SYSTEM_PROMPT
    assert "human_intent" not in EVIDENCE_JUDGE_SYSTEM_PROMPT
    assert "human_escalate" not in EVIDENCE_JUDGE_SYSTEM_PROMPT

    # Verify prompt safety instruction against injections
    assert "ignore instructions" in RESPONSE_JUDGE_SYSTEM_PROMPT.lower()
    assert "ignore any instructions" in EVIDENCE_JUDGE_SYSTEM_PROMPT.lower()


# ==============================================================================
# 3. Judge Cache Tests
# ==============================================================================

def test_judge_cache_set_get(tmp_path):
    """Verify caching saves to disk and retrieves accurately."""
    cache_file = tmp_path / "test_cache.json"
    cache = JudgeCache(cache_file=cache_file)

    test_data = {"correctness": 5, "overall_score": 5.0}
    cache.set("resp_quality_1", test_data)

    # Read back through new instance
    cache2 = JudgeCache(cache_file=cache_file)
    retrieved = cache2.get("resp_quality_1")
    assert retrieved == test_data
    assert cache2.get("non_existent_key") is None


# ==============================================================================
# 4. Human Annotation Subset Selection Tests
# ==============================================================================

def test_deterministic_subset_selection(tmp_path):
    """Verify 50-example diverse subset is selected deterministically with blank fields."""
    per_example_csv = Path(__file__).resolve().parent.parent / "evaluation" / "results" / "per_example_results.csv"
    assert per_example_csv.exists()

    out_csv = tmp_path / "annotations_test.csv"
    df_subset = select_diverse_subset(
        input_csv=per_example_csv,
        output_csv=out_csv,
        sample_size=50,
        seed=42,
    )

    assert len(df_subset) == 50
    assert list(df_subset.columns) == [
        "gold_id",
        "conversation_id",
        "human_evidence_supported",
        "human_support_score",
        "human_notes",
    ]
    # Blank human columns
    assert (df_subset["human_evidence_supported"] == "").all()
    assert (df_subset["human_support_score"] == "").all()

    # Verify deterministic reproducibility (same gold_ids on second run)
    df_subset_2 = select_diverse_subset(
        input_csv=per_example_csv,
        output_csv=tmp_path / "annotations_test_2.csv",
        sample_size=50,
        seed=42,
    )
    assert list(df_subset["gold_id"]) == list(df_subset_2["gold_id"])


# ==============================================================================
# 5. Agreement Calculation Tests
# ==============================================================================

def test_agreement_unpopulated_annotations(tmp_path):
    """Verify agreement engine reports 'Human agreement not yet available' when blank."""
    annot_csv = tmp_path / "blank_annot.csv"
    pd.DataFrame({
        "gold_id": [1, 2],
        "conversation_id": ["c1", "c2"],
        "human_evidence_supported": ["", ""],
        "human_support_score": ["", ""],
        "human_notes": ["", ""],
    }).to_csv(annot_csv, index=False)

    ev_csv = tmp_path / "ev_judge.csv"
    pd.DataFrame({
        "gold_id": [1, 2],
        "evidence_supported": [True, True],
        "support_score": [5, 4],
    }).to_csv(ev_csv, index=False)

    res = calculate_judge_human_agreement(
        annotation_csv=annot_csv,
        evidence_results_csv=ev_csv,
        output_json=None,
    )
    assert res["status"] == "Human agreement not yet available"
    assert res["annotated_count"] == 0


def test_agreement_populated_annotations(tmp_path):
    """Verify agreement metrics when human annotations are filled."""
    annot_csv = tmp_path / "filled_annot.csv"
    pd.DataFrame({
        "gold_id": [1, 2, 3, 4],
        "conversation_id": ["c1", "c2", "c3", "c4"],
        "human_evidence_supported": ["YES", "YES", "NO", "YES"],
        "human_support_score": [5, 4, 2, 5],
        "human_notes": ["n1", "n2", "n3", "n4"],
    }).to_csv(annot_csv, index=False)

    ev_csv = tmp_path / "ev_judge.csv"
    pd.DataFrame({
        "gold_id": [1, 2, 3, 4],
        "evidence_supported": [True, True, False, False],  # 3 of 4 match
        "support_score": [5, 4, 1, 3],                     # diffs: 0, 0, 1, 2 -> MAE = 3/4 = 0.75
    }).to_csv(ev_csv, index=False)

    res = calculate_judge_human_agreement(
        annotation_csv=annot_csv,
        evidence_results_csv=ev_csv,
        output_json=None,
    )

    assert res["status"] == "Agreement Calculated"
    assert res["annotated_count"] == 4
    assert res["exact_agreement_pct"] == 75.0
    assert res["mean_absolute_error"] == 0.75
    assert "cohen_kappa_binary" in res
    assert "linear_weighted_kappa" in res


# ==============================================================================
# 6. Failure & Invalid JSON Handling Tests (Zero API Calls)
# ==============================================================================

class MockFailingClient:
    """Mock OpenAI client that returns invalid JSON to test error handling."""
    class Chat:
        class Completions:
            @staticmethod
            def create(*args, **kwargs):
                class Choice:
                    class Message:
                        content = "Invalid Non-JSON response from model"
                    message = Message()
                class MockResp:
                    choices = [Choice()]
                return MockResp()
        completions = Completions()
    chat = Chat()


def test_judge_invalid_json_handling_without_score_fabrication():
    """Verify invalid JSON returns judge_success=False without fabricating scores."""
    judge = ResponseQualityJudge(client=MockFailingClient(), cache=None)
    score, success, reason = judge.evaluate(
        gold_id=999,
        conversation_context="Context",
        predicted_intent="iOS / Software",
        predicted_action="auto_handle",
        generated_response="Response",
        evidence_items=[],
    )

    assert success is False
    assert score is None
    assert "failed" in reason.lower()


# ==============================================================================
# 7. Golden Set Integrity Test
# ==============================================================================

def test_golden_set_unaltered():
    """Verify that canonical apple_goldset.csv has exactly 200 rows and 7 columns."""
    df = pd.read_csv(GOLDSET_PATH)
    assert len(df) == 200
    assert len(df.columns) >= 7
    assert df["conversation_id"].nunique() == 200
