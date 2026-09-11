"""Phase 9 Final Human vs LLM Evidence Agreement Engine.

Validates human_evidence_review.csv (50 human-reviewed examples),
matches against evidence_judge_results.csv,
computes binary and ordinal agreement metrics,
identifies explicit disagreements,
updates evidence_agreement.json and llm_judge_report.md.
"""

import json
from pathlib import Path
import sys
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

RESULTS_DIR = Path(__file__).resolve().parent / "results"
HUMAN_REVIEW_CSV = RESULTS_DIR / "human_evidence_review.csv"
EVIDENCE_JUDGE_CSV = RESULTS_DIR / "evidence_judge_results.csv"
AGREEMENT_JSON = RESULTS_DIR / "evidence_agreement.json"
REPORT_MD = RESULTS_DIR / "llm_judge_report.md"


def run_agreement_analysis() -> Dict[str, Any]:
    print("=" * 75)
    print("PHASE 9: HUMAN VS LLM EVIDENCE GROUNDING AGREEMENT")
    print("=" * 75)

    # --------------------------------------------------------------------------
    # Step 1: Validate human_evidence_review.csv
    # --------------------------------------------------------------------------
    if not HUMAN_REVIEW_CSV.exists():
        raise FileNotFoundError(f"File not found: {HUMAN_REVIEW_CSV}")

    df_human = pd.read_csv(HUMAN_REVIEW_CSV)

    # Validation checks
    if len(df_human) != 50:
        raise ValueError(f"Validation failure: Expected exactly 50 rows, found {len(df_human)}.")

    if df_human["gold_id"].nunique() != 50:
        raise ValueError(f"Validation failure: Expected 50 unique gold_ids, found {df_human['gold_id'].nunique()}.")

    if df_human["human_evidence_supported"].isna().any():
        missing_count = int(df_human["human_evidence_supported"].isna().sum())
        raise ValueError(f"Validation failure: Missing human_evidence_supported in {missing_count} rows.")

    if df_human["human_support_score"].isna().any():
        missing_count = int(df_human["human_support_score"].isna().sum())
        raise ValueError(f"Validation failure: Missing human_support_score in {missing_count} rows.")

    human_decisions = [str(x).strip().upper() for x in df_human["human_evidence_supported"]]
    invalid_decisions = set(human_decisions) - {"YES", "NO"}
    if invalid_decisions:
        raise ValueError(f"Validation failure: Invalid human_evidence_supported values: {invalid_decisions}")

    human_scores = [int(round(float(x))) for x in df_human["human_support_score"]]
    invalid_scores = [s for s in human_scores if s not in [0, 1, 2, 3, 4, 5]]
    if invalid_scores:
        raise ValueError(f"Validation failure: Support scores outside 0-5 found: {invalid_scores}")

    print("Step 1: Validation PASSED! Exactly 50 human annotations validated (50/50).")

    # --------------------------------------------------------------------------
    # Step 2: Match with LLM Judge Results
    # --------------------------------------------------------------------------
    if not EVIDENCE_JUDGE_CSV.exists():
        raise FileNotFoundError(f"File not found: {EVIDENCE_JUDGE_CSV}")

    df_judge = pd.read_csv(EVIDENCE_JUDGE_CSV)

    # Merge on gold_id
    merged = pd.merge(
        df_human[[
            "gold_id", "conversation_id", "human_evidence_supported",
            "human_support_score", "human_notes"
        ]],
        df_judge[[
            "gold_id", "evidence_supported", "support_score",
            "supported_claims", "unsupported_claims", "judge_reason"
        ]],
        on="gold_id",
        suffixes=("_human", "_judge")
    )

    if len(merged) != 50:
        raise ValueError(f"Merge error: Expected 50 matched rows, got {len(merged)}")

    print(f"Step 2: Successfully matched all 50 human annotations with LLM judge results.")

    # --------------------------------------------------------------------------
    # Step 3: Binary Agreement
    # --------------------------------------------------------------------------
    # Standardize to boolean / 1/0
    y_human_bin = [1 if str(x).strip().upper() == "YES" else 0 for x in merged["human_evidence_supported"]]
    y_judge_bin = [1 if bool(x) or str(x).lower() == "true" else 0 for x in merged["evidence_supported"]]

    yes_yes = sum(1 for h, j in zip(y_human_bin, y_judge_bin) if h == 1 and j == 1)
    yes_no = sum(1 for h, j in zip(y_human_bin, y_judge_bin) if h == 1 and j == 0)
    no_yes = sum(1 for h, j in zip(y_human_bin, y_judge_bin) if h == 0 and j == 1)
    no_no = sum(1 for h, j in zip(y_human_bin, y_judge_bin) if h == 0 and j == 0)

    exact_agreement_count = yes_yes + no_no
    exact_agreement_pct = round(exact_agreement_count / 50.0 * 100.0, 2)

    cohen_kappa = round(float(cohen_kappa_score(y_human_bin, y_judge_bin)), 4)

    # --------------------------------------------------------------------------
    # Step 4: Score Agreement (0-5 scale)
    # --------------------------------------------------------------------------
    scores_human = [float(s) for s in merged["human_support_score"]]
    scores_judge = [float(s) for s in merged["support_score"]]

    mean_human_score = round(float(np.mean(scores_human)), 2)
    mean_judge_score = round(float(np.mean(scores_judge)), 2)

    diffs = [abs(h - j) for h, j in zip(scores_human, scores_judge)]
    mae = round(float(np.mean(diffs)), 4)

    exact_score_count = sum(1 for d in diffs if d == 0)
    exact_score_pct = round(exact_score_count / 50.0 * 100.0, 2)

    within_1_count = sum(1 for d in diffs if d <= 1.0)
    within_1_pct = round(within_1_count / 50.0 * 100.0, 2)

    int_scores_human = [int(round(s)) for s in scores_human]
    int_scores_judge = [int(round(s)) for s in scores_judge]

    linear_kappa = round(float(cohen_kappa_score(int_scores_human, int_scores_judge, weights="linear")), 4)
    quadratic_kappa = round(float(cohen_kappa_score(int_scores_human, int_scores_judge, weights="quadratic")), 4)

    # --------------------------------------------------------------------------
    # Step 5: Identify Disagreements
    # --------------------------------------------------------------------------
    disagreements = []
    for _, r in merged.iterrows():
        h_bin = 1 if str(r["human_evidence_supported"]).strip().upper() == "YES" else 0
        j_bin = 1 if bool(r["evidence_supported"]) or str(r["evidence_supported"]).lower() == "true" else 0
        h_score = int(round(float(r["human_support_score"])))
        j_score = int(round(float(r["support_score"])))
        diff = abs(h_score - j_score)

        is_binary_disagree = (h_bin != j_bin)
        is_score_disagree = (diff >= 2)

        if is_binary_disagree or is_score_disagree:
            supp_claims = r["supported_claims"] if pd.notna(r["supported_claims"]) and str(r["supported_claims"]).lower() != "nan" else "None"
            unsupp_claims = r["unsupported_claims"] if pd.notna(r["unsupported_claims"]) and str(r["unsupported_claims"]).lower() != "nan" else "None"
            disagreements.append({
                "gold_id": int(r["gold_id"]),
                "conversation_id": str(r["conversation_id"]),
                "disagreement_type": "Binary & Score (>=2)" if (is_binary_disagree and is_score_disagree) else ("Binary Flip" if is_binary_disagree else "Score Gap >= 2"),
                "human_judgment": str(r["human_evidence_supported"]).strip().upper(),
                "human_score": h_score,
                "human_notes": str(r["human_notes"]).strip() if pd.notna(r["human_notes"]) else "",
                "llm_judgment": "YES" if j_bin == 1 else "NO",
                "llm_score": j_score,
                "llm_supported_claims": str(supp_claims),
                "llm_unsupported_claims": str(unsupp_claims),
                "llm_reason": str(r["judge_reason"]).strip() if pd.notna(r["judge_reason"]) else "",
            })

    # --------------------------------------------------------------------------
    # Step 6: Create/Update evidence_agreement.json
    # --------------------------------------------------------------------------
    agreement_payload = {
        "status": "Agreement Validated and Calculated",
        "sample_size": 50,
        "human_annotations_validated": "50/50",
        "binary_agreement": {
            "yes_yes": yes_yes,
            "yes_no": yes_no,
            "no_yes": no_yes,
            "no_no": no_no,
            "exact_agreement_count": exact_agreement_count,
            "exact_agreement_pct": exact_agreement_pct,
            "cohen_kappa": cohen_kappa,
            "interpretation": _interpret_kappa(cohen_kappa),
        },
        "score_agreement": {
            "mean_human_score": mean_human_score,
            "mean_llm_score": mean_judge_score,
            "mean_absolute_error": mae,
            "exact_score_agreement_count": exact_score_count,
            "exact_score_agreement_pct": exact_score_pct,
            "agreement_within_plus_minus_1_count": within_1_count,
            "agreement_within_plus_minus_1_pct": within_1_pct,
            "linear_weighted_kappa": linear_kappa,
            "quadratic_weighted_kappa": quadratic_kappa,
        },
        "disagreements": {
            "total_disagreements": len(disagreements),
            "human_yes_llm_no_count": yes_no,
            "human_no_llm_yes_count": no_yes,
            "score_diff_ge_2_count": sum(1 for d in diffs if d >= 2),
            "items": disagreements,
        },
        "governance_note": (
            "LLM judging was performed on 200 Golden Set examples. Human-vs-LLM agreement "
            "was performed on a 50-example subset. Agreement results must not be generalized "
            "to all 200 examples."
        ),
    }

    with open(AGREEMENT_JSON, "w", encoding="utf-8") as f:
        json.dump(agreement_payload, f, indent=2)
    print(f"Step 6: Successfully updated {AGREEMENT_JSON}")

    # --------------------------------------------------------------------------
    # Step 7: Update llm_judge_report.md
    # --------------------------------------------------------------------------
    _update_markdown_report(agreement_payload)
    print(f"Step 7: Successfully updated {REPORT_MD}")

    return agreement_payload


def _interpret_kappa(kappa: float) -> str:
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


def _update_markdown_report(data: Dict[str, Any]) -> None:
    """Read llm_judge_report.md, update Section 8 with empirical agreement metrics and governance notes."""
    if not REPORT_MD.exists():
        return

    bin_ag = data["binary_agreement"]
    sc_ag = data["score_agreement"]
    dis = data["disagreements"]

    sec8_md = f"""## 8. Judge–Human Agreement (Empirical 50-Example Audit)

> [!IMPORTANT]
> **Evaluation Boundary & Governance Notice**:
> - LLM judging was performed on **200 Golden Set examples**.
> - Human-vs-LLM agreement was performed on a **50-example diverse subset**.
> - Agreement results reflect this 50-sample human benchmark and **must not be generalized to all 200 examples**.

### A. Binary Grounding Agreement (YES/NO)
- **Human Annotations Validated**: **50/50**
- **Exact Agreement**: **{bin_ag['exact_agreement_pct']}%** ({bin_ag['exact_agreement_count']}/50 examples)
- **Contingency Matrix**:
  - **Both YES (Supported)**: **{bin_ag['yes_yes']}**
  - **Both NO (Unsupported)**: **{bin_ag['no_no']}**
  - **Human YES / LLM NO**: **{bin_ag['yes_no']}**
  - **Human NO / LLM YES**: **{bin_ag['no_yes']}**
- **Cohen's Kappa (Binary)**: **{bin_ag['cohen_kappa']:.4f}** (*{bin_ag['interpretation']}*)

### B. Ordinal Score Agreement (0–5 Scale)
- **Mean Human Support Score**: **{sc_ag['mean_human_score']:.2f} / 5.0**
- **Mean LLM Support Score**: **{sc_ag['mean_llm_score']:.2f} / 5.0**
- **Mean Absolute Error (MAE)**: **{sc_ag['mean_absolute_error']:.4f}**
- **Exact Score Agreement**: **{sc_ag['exact_score_agreement_pct']}%** ({sc_ag['exact_score_agreement_count']}/50)
- **Agreement within ±1 Point**: **{sc_ag['agreement_within_plus_minus_1_pct']}%** ({sc_ag['agreement_within_plus_minus_1_count']}/50)
- **Linear Weighted Kappa**: **{sc_ag['linear_weighted_kappa']:.4f}**
- **Quadratic Weighted Kappa**: **{sc_ag['quadratic_weighted_kappa']:.4f}**

### C. Disagreement Analysis ({dis['total_disagreements']} cases with binary flip or score gap ≥ 2)
"""

    if dis["items"]:
        sec8_md += "| Gold ID | Human Judgment (Score) | LLM Judgment (Score) | Human Notes | LLM Unsupported Claims / Reason |\n"
        sec8_md += "| :---: | :---: | :---: | :--- | :--- |\n"
        for item in dis["items"]:
            h_str = f"**{item['human_judgment']}** ({item['human_score']})"
            l_str = f"**{item['llm_judgment']}** ({item['llm_score']})"
            h_note = item['human_notes'].replace("\n", " ").replace("|", "\\|")[:80]
            l_reason = item['llm_reason'].replace("\n", " ").replace("|", "\\|")[:80]
            sec8_md += f"| #{item['gold_id']} | {h_str} | {l_str} | {h_note}... | {l_reason}... |\n"
    else:
        sec8_md += "\n*Zero binary flips or score deviations ≥ 2 were detected between human annotators and LLM judges.*\n"

    # Replace Section 8 in markdown
    with open(REPORT_MD, "r", encoding="utf-8") as f:
        content = f.read()

    # Find Section 8 boundary
    sec8_start = content.find("## 8. Judge–Human Agreement")
    if sec8_start == -1:
        sec8_start = content.find("## 8. Judge-Human Agreement")

    if sec8_start != -1:
        sec9_start = content.find("## 9. Limitations", sec8_start)
        if sec9_start != -1:
            new_content = content[:sec8_start] + sec8_md + "\n" + content[sec9_start:]
        else:
            new_content = content[:sec8_start] + sec8_md
    else:
        new_content = content + "\n\n" + sec8_md

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(new_content)


if __name__ == "__main__":
    run_agreement_analysis()
