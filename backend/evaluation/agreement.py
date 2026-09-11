"""Judge–Human Agreement Analysis Engine.

Calculates statistical agreement between the automated LLM Evidence Judge
and human evidence annotations across:
1. Exact Agreement (%) on binary evidence support (YES/NO)
2. Cohen's Kappa (binary classification reliability)
3. Linear & Quadratic Weighted Cohen's Kappa (0-5 ordinal score reliability)
4. Mean Absolute Error (MAE) on 0-5 scale

Strictly handles unpopulated annotations by returning "Human agreement not yet available".
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

logger = logging.getLogger("evaluation.agreement")

DEFAULT_ANNOTATION_CSV = Path(__file__).resolve().parent / "evidence_human_annotations.csv"
DEFAULT_EVIDENCE_RESULTS_CSV = Path(__file__).resolve().parent / "results" / "evidence_judge_results.csv"
DEFAULT_AGREEMENT_JSON = Path(__file__).resolve().parent / "results" / "evidence_agreement.json"


def calculate_judge_human_agreement(
    annotation_csv: Path = DEFAULT_ANNOTATION_CSV,
    evidence_results_csv: Path = DEFAULT_EVIDENCE_RESULTS_CSV,
    output_json: Optional[Path] = DEFAULT_AGREEMENT_JSON,
) -> Dict[str, Any]:
    """Calculate agreement metrics between human annotations and LLM judge.

    Args:
        annotation_csv: Path to evidence_human_annotations.csv.
        evidence_results_csv: Path to evidence_judge_results.csv.
        output_json: Optional path to persist evidence_agreement.json.

    Returns:
        Dict containing statistical agreement metrics or availability status.
    """
    annotation_path = Path(annotation_csv)
    evidence_path = Path(evidence_results_csv)

    if not annotation_path.exists():
        res = {
            "status": "Human agreement not yet available",
            "message": f"Annotation file not found at: {annotation_path}",
            "sample_size": 0,
        }
        if output_json:
            _save_json(res, output_json)
        return res

    df_annot = pd.read_csv(annotation_path)

    # Check if human columns exist and have non-null, non-empty entries
    required_cols = ["gold_id", "human_evidence_supported", "human_support_score"]
    if not all(col in df_annot.columns for col in required_cols):
        res = {
            "status": "Human agreement not yet available",
            "message": "Annotation file missing required columns.",
            "sample_size": len(df_annot),
        }
        if output_json:
            _save_json(res, output_json)
        return res

    # Filter for populated rows
    valid_mask = (
        df_annot["human_evidence_supported"].notna()
        & (df_annot["human_evidence_supported"].astype(str).str.strip() != "")
        & df_annot["human_support_score"].notna()
        & (df_annot["human_support_score"].astype(str).str.strip() != "")
    )
    populated_df = df_annot[valid_mask].copy()

    if len(populated_df) == 0:
        res = {
            "status": "Human agreement not yet available",
            "message": (
                "Human evidence annotations in evidence_human_annotations.csv are currently unpopulated. "
                "Agreement metrics will be calculated once real human labels are entered."
            ),
            "sample_size": len(df_annot),
            "annotated_count": 0,
        }
        if output_json:
            _save_json(res, output_json)
        return res

    if not evidence_path.exists():
        res = {
            "status": "Human agreement not yet available",
            "message": f"Evidence judge results not found at: {evidence_path}",
            "sample_size": len(df_annot),
            "annotated_count": len(populated_df),
        }
        if output_json:
            _save_json(res, output_json)
        return res

    df_judge = pd.read_csv(evidence_path)
    merged = pd.merge(populated_df, df_judge, on="gold_id", suffixes=("_human", "_judge"))

    if len(merged) == 0:
        res = {
            "status": "Human agreement not yet available",
            "message": "No overlapping gold_ids between annotations and judge results.",
            "sample_size": len(df_annot),
            "annotated_count": len(populated_df),
        }
        if output_json:
            _save_json(res, output_json)
        return res

    # 1. Binary Agreement (YES/NO)
    y_human_bin = [1 if str(v).strip().upper() == "YES" else 0 for v in merged["human_evidence_supported"]]
    y_judge_bin = [1 if bool(v) or str(v).lower() == "true" else 0 for v in merged["evidence_supported"]]

    exact_matches = sum(1 for h, j in zip(y_human_bin, y_judge_bin) if h == j)
    exact_agreement_pct = round(exact_matches / len(merged) * 100.0, 2)

    try:
        binary_kappa = round(float(cohen_kappa_score(y_human_bin, y_judge_bin)), 4)
    except Exception:
        binary_kappa = 0.0

    # 2. Ordinal Score Agreement (0-5)
    y_human_score = [float(v) for v in merged["human_support_score"]]
    y_judge_score = [float(v) for v in merged["support_score"]]

    score_differences = [abs(h - j) for h, j in zip(y_human_score, y_judge_score)]
    mae = round(float(np.mean(score_differences)), 4)

    try:
        linear_kappa = round(float(cohen_kappa_score(
            [int(round(s)) for s in y_human_score],
            [int(round(s)) for s in y_judge_score],
            weights="linear"
        )), 4)
    except Exception:
        linear_kappa = 0.0

    try:
        quadratic_kappa = round(float(cohen_kappa_score(
            [int(round(s)) for s in y_human_score],
            [int(round(s)) for s in y_judge_score],
            weights="quadratic"
        )), 4)
    except Exception:
        quadratic_kappa = 0.0

    res = {
        "status": "Agreement Calculated",
        "annotation_sample_size": len(df_annot),
        "annotated_count": len(merged),
        "exact_agreement_pct": exact_agreement_pct,
        "cohen_kappa_binary": binary_kappa,
        "linear_weighted_kappa": linear_kappa,
        "quadratic_weighted_kappa": quadratic_kappa,
        "mean_absolute_error": mae,
        "interpretation": _interpret_kappa(binary_kappa),
    }

    if output_json:
        _save_json(res, output_json)

    return res


def _interpret_kappa(kappa: float) -> str:
    """Provide standard Landis & Koch (1977) interpretation of Cohen's Kappa."""
    if kappa < 0:
        return "Poor agreement (less than chance)"
    elif kappa <= 0.20:
        return "Slight agreement"
    elif kappa <= 0.40:
        return "Fair agreement"
    elif kappa <= 0.60:
        return "Moderate agreement"
    elif kappa <= 0.80:
        return "Substantial agreement"
    else:
        return "Almost perfect agreement"


def _save_json(data: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
