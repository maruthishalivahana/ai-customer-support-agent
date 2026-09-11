"""Evaluation Report and Artifact Generator.

Saves evaluation outputs into `backend/evaluation/results/`:
1. results.json - Full machine-readable evaluation summary
2. per_example_results.csv - Granular row-by-row predictions and safety audits
3. intent_metrics.csv - Per-intent precision, recall, F1, and support
4. confusion_matrix.csv - 12x12 Intent Confusion Matrix
5. baseline_comparison.csv - Model vs Baseline comparative metrics

Also formats a comprehensive terminal report.
"""

import json
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def save_evaluation_artifacts(
    evaluation_summary: Dict[str, Any],
    per_example_rows: List[Dict[str, Any]],
    intent_metrics_table: List[Dict[str, Any]],
    confusion_matrix_df: pd.DataFrame,
    baseline_comparison_df: pd.DataFrame,
    output_dir: Path = DEFAULT_RESULTS_DIR,
) -> Dict[str, Path]:
    """Save all evaluation artifacts to the results directory.

    Args:
        evaluation_summary: Dict containing full hierarchical metrics.
        per_example_rows: List of dicts for each of the 200 examples.
        intent_metrics_table: List of dicts with per-intent precision/recall/F1/support.
        confusion_matrix_df: 12x12 DataFrame of intent confusion matrix.
        baseline_comparison_df: DataFrame comparing Agent, Simple TF-IDF, and Majority baselines.
        output_dir: Path to directory where results are stored.

    Returns:
        Dict mapping artifact names to their saved file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = {}

    # 1. results.json
    results_json_path = output_dir / "results.json"
    # Convert any non-serializable objects (like DataFrame)
    summary_to_save = dict(evaluation_summary)
    if "agent_intent_metrics" in summary_to_save and "confusion_matrix" in summary_to_save["agent_intent_metrics"]:
        cm = summary_to_save["agent_intent_metrics"]["confusion_matrix"]
        if isinstance(cm, pd.DataFrame):
            summary_to_save["agent_intent_metrics"]["confusion_matrix"] = cm.to_dict()

    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_to_save, f, indent=2, default=str)
    saved_paths["results_json"] = results_json_path

    # 2. per_example_results.csv
    per_example_path = output_dir / "per_example_results.csv"
    per_example_df = pd.DataFrame(per_example_rows)
    per_example_df.to_csv(per_example_path, index=False)
    saved_paths["per_example_csv"] = per_example_path

    # 3. intent_metrics.csv
    intent_metrics_path = output_dir / "intent_metrics.csv"
    intent_df = pd.DataFrame(intent_metrics_table)
    intent_df.to_csv(intent_metrics_path, index=False)
    saved_paths["intent_metrics_csv"] = intent_metrics_path

    # 4. confusion_matrix.csv
    cm_path = output_dir / "confusion_matrix.csv"
    confusion_matrix_df.to_csv(cm_path, index=True)
    saved_paths["confusion_matrix_csv"] = cm_path

    # 5. baseline_comparison.csv
    baseline_path = output_dir / "baseline_comparison.csv"
    baseline_comparison_df.to_csv(baseline_path, index=False)
    saved_paths["baseline_comparison_csv"] = baseline_path

    return saved_paths


def print_terminal_report(
    summary: Dict[str, Any],
    baseline_df: pd.DataFrame,
    intent_df: pd.DataFrame,
) -> None:
    """Format and print a clean, comprehensive terminal report."""
    line = "=" * 80
    subline = "-" * 80

    print("\n" + line)
    print("      PHASE 8: GOLDEN SET BENCHMARK & EVALUATION HARNESS REPORT")
    print(line)

    dataset_info = summary.get("dataset", {})
    print(f"Dataset:              data/apple_goldset.csv")
    print(f"Total Evaluated:      {dataset_info.get('total_examples', 200)} examples")
    print(f"Unique Conversations: {dataset_info.get('unique_conversations', 200)}")
    print(f"Escalation Ground-Truth: {dataset_info.get('escalate_yes_count', 26)} YES | {dataset_info.get('escalate_no_count', 174)} NO")

    print("\n" + subline)
    print("1. MODEL COMPARISON (INTENT CLASSIFICATION)")
    print(subline)
    print(baseline_df.to_string(index=False))

    agent_metrics = summary.get("agent_intent_metrics", {})
    zero_support = agent_metrics.get("zero_support_classes", [])
    if zero_support:
        print(f"\nNote on Zero-Support Classes: {', '.join(zero_support)} (0 examples in Golden Set)")

    print("\n" + subline)
    print("2. PER-INTENT METRICS (AGENT)")
    print(subline)
    print(intent_df.to_string(index=False))

    dec_metrics = summary.get("decision_and_safety_metrics", {})
    action_dist = dec_metrics.get("action_distribution", {})
    esc_det = dec_metrics.get("escalation_detection", {})
    safety = dec_metrics.get("autohandle_safety", {})

    print("\n" + subline)
    print("3. DECISION POLICY & SAFETY METRICS")
    print(subline)
    print("Action Distribution:")
    for action, vals in action_dist.items():
        print(f"  - {action:12s}: {vals['count']:3d} ({vals['percentage']:5.1f}%)")

    print("\nHuman Escalation Detection (escalate vs Human YES):")
    print(f"  - Precision:        {esc_det.get('precision', 0.0):.4f}")
    print(f"  - Recall:           {esc_det.get('recall', 0.0):.4f}")
    print(f"  - F1 Score:         {esc_det.get('f1', 0.0):.4f}")
    cm_esc = esc_det.get("confusion_matrix", {})
    print(f"  - Confusion Matrix: TP={cm_esc.get('tp', 0)}, FP={cm_esc.get('fp', 0)}, FN={cm_esc.get('fn', 0)}, TN={cm_esc.get('tn', 0)}")

    print("\nAuto-Handle Safety:")
    print(f"  - Total Auto-Handled:       {safety.get('total_autohandled', 0)}")
    print(f"  - Safe Auto-Handled (NO):   {safety.get('safe_autohandled', 0)}")
    print(f"  - Unsafe Auto-Handled (YES):{safety.get('unsafe_autohandled', 0)}")
    print(f"  - Auto-Handle Precision:    {safety.get('autohandle_precision_wrt_no', 0.0):.4f} (Safe / Total Auto-Handled)")
    print(f"  - Unsafe Auto-Handle Rate:  {safety.get('unsafe_autohandle_rate', 0.0):.4f} (Unsafe / Total Auto-Handled)")

    print("\n" + line)
    print("Evaluation artifacts saved to: backend/evaluation/results/")
    print(line + "\n")
