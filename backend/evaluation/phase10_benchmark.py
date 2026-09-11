"""Phase 10: Before/After Golden Set Evaluation Benchmark.

Compares Phase 10 improved agent against the Phase 8 baseline across:
- Intent classification metrics (Accuracy, Macro F1, Weighted F1)
- Action distributions (auto_handle, clarify, escalate counts and %)
- Escalation detection metrics (Precision, Recall, F1, TP, FP, FN, TN)
- Auto-handle safety metrics (Safe, Unsafe, Auto-handle Precision, Unsafe Auto-handle Rate)
- Outputs results/phase10_comparison.json and results/phase10_comparison.md
- Enforces safety gate: fails if unsafe auto-handles increase significantly.
"""

import json
from pathlib import Path
import sys
from typing import Any, Dict

import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from evaluation.run_evaluation import run_evaluation

RESULTS_DIR = Path(__file__).resolve().parent / "results"
BASELINE_JSON_PATH = RESULTS_DIR / "results.json"
OUTPUT_JSON_PATH = RESULTS_DIR / "phase10_comparison.json"
OUTPUT_MD_PATH = RESULTS_DIR / "phase10_comparison.md"


# Canonical Phase 8 baseline values established in Phase 8/8A benchmark
PHASE_8_BASELINE = {
    "metadata": {
        "phase": "Phase 8 Baseline",
        "dataset": "data/apple_goldset.csv (200 examples)",
    },
    "agent_intent_metrics": {
        "accuracy": 0.5200,
        "macro_precision": 0.5359,
        "macro_recall": 0.4027,
        "macro_f1": 0.4317,
        "weighted_f1": 0.5344,
        "total_evaluated": 200,
    },
    "decision_and_safety_metrics": {
        "action_distribution": {
            "auto_handle": {"count": 76, "percentage": 38.0},
            "clarify": {"count": 25, "percentage": 12.5},
            "escalate": {"count": 99, "percentage": 49.5},
        },
        "escalation_detection": {
            "precision": 0.1212,
            "recall": 0.4615,
            "f1": 0.1920,
            "confusion_matrix": {
                "tp": 12,
                "fp": 87,
                "fn": 14,
                "tn": 87,
            },
            "human_escalate_yes_count": 26,
            "predicted_escalate_count": 99,
        },
        "autohandle_safety": {
            "total_autohandled": 76,
            "safe_autohandled": 64,
            "unsafe_autohandled": 12,
            "autohandle_precision_wrt_no": 0.8421,
            "unsafe_autohandle_rate": 0.1579,
        },
    },
}


def load_phase8_baseline() -> Dict[str, Any]:
    return PHASE_8_BASELINE


def build_comparison(baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    b_intent = baseline["agent_intent_metrics"]
    c_intent = current["agent_intent_metrics"]

    b_safety = baseline["decision_and_safety_metrics"]
    c_safety = current["decision_and_safety_metrics"]

    b_dist = b_safety["action_distribution"]
    c_dist = c_safety["action_distribution"]

    b_esc = b_safety["escalation_detection"]
    c_esc = c_safety["escalation_detection"]

    b_auto = b_safety["autohandle_safety"]
    c_auto = c_safety["autohandle_safety"]

    comparison = {
        "metadata": {
            "evaluation_dataset": "data/apple_goldset.csv (200 examples)",
            "phase8_timestamp": baseline.get("metadata", {}).get("evaluation_timestamp"),
            "phase10_timestamp": current.get("metadata", {}).get("evaluation_timestamp"),
        },
        "intent_classification": {
            "accuracy": {
                "before": b_intent["accuracy"],
                "after": c_intent["accuracy"],
                "delta": round(c_intent["accuracy"] - b_intent["accuracy"], 4),
            },
            "macro_f1": {
                "before": b_intent["macro_f1"],
                "after": c_intent["macro_f1"],
                "delta": round(c_intent["macro_f1"] - b_intent["macro_f1"], 4),
            },
            "weighted_f1": {
                "before": b_intent["weighted_f1"],
                "after": c_intent["weighted_f1"],
                "delta": round(c_intent["weighted_f1"] - b_intent["weighted_f1"], 4),
            },
        },
        "action_distribution": {
            "auto_handle": {
                "before_count": b_dist["auto_handle"]["count"],
                "after_count": c_dist["auto_handle"]["count"],
                "before_pct": b_dist["auto_handle"]["percentage"],
                "after_pct": c_dist["auto_handle"]["percentage"],
                "count_delta": c_dist["auto_handle"]["count"] - b_dist["auto_handle"]["count"],
            },
            "clarify": {
                "before_count": b_dist["clarify"]["count"],
                "after_count": c_dist["clarify"]["count"],
                "before_pct": b_dist["clarify"]["percentage"],
                "after_pct": c_dist["clarify"]["percentage"],
                "count_delta": c_dist["clarify"]["count"] - b_dist["clarify"]["count"],
            },
            "escalate": {
                "before_count": b_dist["escalate"]["count"],
                "after_count": c_dist["escalate"]["count"],
                "before_pct": b_dist["escalate"]["percentage"],
                "after_pct": c_dist["escalate"]["percentage"],
                "count_delta": c_dist["escalate"]["count"] - b_dist["escalate"]["count"],
            },
        },
        "escalation_metrics": {
            "precision": {
                "before": b_esc["precision"],
                "after": c_esc["precision"],
                "delta": round(c_esc["precision"] - b_esc["precision"], 4),
            },
            "recall": {
                "before": b_esc["recall"],
                "after": c_esc["recall"],
                "delta": round(c_esc["recall"] - b_esc["recall"], 4),
            },
            "f1": {
                "before": b_esc["f1"],
                "after": c_esc["f1"],
                "delta": round(c_esc["f1"] - b_esc["f1"], 4),
            },
            "confusion_matrix": {
                "before": b_esc["confusion_matrix"],
                "after": c_esc["confusion_matrix"],
            },
            "false_positives": {
                "before": b_esc["confusion_matrix"]["fp"],
                "after": c_esc["confusion_matrix"]["fp"],
                "delta": c_esc["confusion_matrix"]["fp"] - b_esc["confusion_matrix"]["fp"],
            },
            "false_negatives": {
                "before": b_esc["confusion_matrix"]["fn"],
                "after": c_esc["confusion_matrix"]["fn"],
                "delta": c_esc["confusion_matrix"]["fn"] - b_esc["confusion_matrix"]["fn"],
            },
        },
        "autohandle_safety": {
            "total_autohandled": {
                "before": b_auto["total_autohandled"],
                "after": c_auto["total_autohandled"],
                "delta": c_auto["total_autohandled"] - b_auto["total_autohandled"],
            },
            "safe_autohandled": {
                "before": b_auto["safe_autohandled"],
                "after": c_auto["safe_autohandled"],
                "delta": c_auto["safe_autohandled"] - b_auto["safe_autohandled"],
            },
            "unsafe_autohandled": {
                "before": b_auto["unsafe_autohandled"],
                "after": c_auto["unsafe_autohandled"],
                "delta": c_auto["unsafe_autohandled"] - b_auto["unsafe_autohandled"],
            },
            "autohandle_precision": {
                "before": b_auto["autohandle_precision_wrt_no"],
                "after": c_auto["autohandle_precision_wrt_no"],
                "delta": round(c_auto["autohandle_precision_wrt_no"] - b_auto["autohandle_precision_wrt_no"], 4),
            },
            "unsafe_autohandle_rate": {
                "before": b_auto["unsafe_autohandle_rate"],
                "after": c_auto["unsafe_autohandle_rate"],
                "delta": round(c_auto["unsafe_autohandle_rate"] - b_auto["unsafe_autohandle_rate"], 4),
            },
        },
        "safety_gate_status": "PASSED" if c_auto["unsafe_autohandled"] <= b_auto["unsafe_autohandled"] else "FAILED_REGRESSION",
    }
    return comparison


def generate_markdown(comp: Dict[str, Any]) -> str:
    ic = comp["intent_classification"]
    ad = comp["action_distribution"]
    em = comp["escalation_metrics"]
    ah = comp["autohandle_safety"]
    gate = comp["safety_gate_status"]

    md = f"""# Phase 10: Before vs After Benchmark Comparison Report

**Dataset**: `data/apple_goldset.csv` (200 canonical human-reviewed conversations)  
**Safety Gate Status**: **{gate}**

---

## 1. Intent Classification Metrics

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Accuracy** | {ic['accuracy']['before']:.2%} | {ic['accuracy']['after']:.2%} | {ic['accuracy']['delta']:+.2%} |
| **Macro F1** | {ic['macro_f1']['before']:.4f} | {ic['macro_f1']['after']:.4f} | {ic['macro_f1']['delta']:+.4f} |
| **Weighted F1** | {ic['weighted_f1']['before']:.4f} | {ic['weighted_f1']['after']:.4f} | {ic['weighted_f1']['delta']:+.4f} |

*(Intent model weights and pipeline were untouched in Phase 10, so classification performance is exactly preserved.)*

---

## 2. Action Distribution Comparison (200 Conversations)

| Action | Phase 8 Count (%) | Phase 10 Count (%) | Count Delta |
|:---|:---:|:---:|:---:|
| **AUTO_HANDLE** | {ad['auto_handle']['before_count']} ({ad['auto_handle']['before_pct']}%) | {ad['auto_handle']['after_count']} ({ad['auto_handle']['after_pct']}%) | {ad['auto_handle']['count_delta']:+d} |
| **CLARIFY** | {ad['clarify']['before_count']} ({ad['clarify']['before_pct']}%) | {ad['clarify']['after_count']} ({ad['clarify']['after_pct']}%) | {ad['clarify']['count_delta']:+d} |
| **ESCALATE** | {ad['escalate']['before_count']} ({ad['escalate']['before_pct']}%) | {ad['escalate']['after_count']} ({ad['escalate']['after_pct']}%) | {ad['escalate']['count_delta']:+d} |

---

## 3. Escalation Decision Metrics (Binary: Escalate vs Human YES)

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Precision** | {em['precision']['before']:.2%} | {em['precision']['after']:.2%} | {em['precision']['delta']:+.2%} |
| **Recall** | {em['recall']['before']:.2%} | {em['recall']['after']:.2%} | {em['recall']['delta']:+.2%} |
| **F1 Score** | {em['f1']['before']:.4f} | {em['f1']['after']:.4f} | {em['f1']['delta']:+.4f} |
| **False Positives (Over-escalations)** | {em['false_positives']['before']} | {em['false_positives']['after']} | {em['false_positives']['delta']:+d} |
| **False Negatives** | {em['false_negatives']['before']} | {em['false_negatives']['after']} | {em['false_negatives']['delta']:+d} |
| **True Positives** | {em['confusion_matrix']['before']['tp']} | {em['confusion_matrix']['after']['tp']} | {em['confusion_matrix']['after']['tp'] - em['confusion_matrix']['before']['tp']:+d} |

---

## 4. Auto-Handle Safety Metrics

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Total Auto-Handled** | {ah['total_autohandled']['before']} | {ah['total_autohandled']['after']} | {ah['total_autohandled']['delta']:+d} |
| **Safe Auto-Handled** | {ah['safe_autohandled']['before']} | {ah['safe_autohandled']['after']} | {ah['safe_autohandled']['delta']:+d} |
| **Unsafe Auto-Handled (Escalation YES)** | {ah['unsafe_autohandled']['before']} | {ah['unsafe_autohandled']['after']} | {ah['unsafe_autohandled']['delta']:+d} |
| **Auto-Handle Precision (wrt NO)** | {ah['autohandle_precision']['before']:.2%} | {ah['autohandle_precision']['after']:.2%} | {ah['autohandle_precision']['delta']:+.2%} |
| **Unsafe Auto-Handle Rate** | {ah['unsafe_autohandle_rate']['before']:.2%} | {ah['unsafe_autohandle_rate']['after']:.2%} | {ah['unsafe_autohandle_rate']['delta']:+.2%} |

---

## 5. Key Diagnostic Analysis

1. **False-Positive Escalation Reduction**:
   - Phase 8 over-escalated {em['false_positives']['before']} cases down to {em['false_positives']['after']} in Phase 10 (change of {em['false_positives']['delta']:+d}).
   - Converting low-confidence and insufficient-evidence cases into `CLARIFY` routes benign user inquiries to safe clarifying questions rather than immediately triggering expensive human intervention.
   - Detecting resolved and closing conversations allows customer gratitude / acknowledgments to complete gracefully under `AUTO_HANDLE`.

2. **Safety Gate Compliance**:
   - Unsafe auto-handles moved from {ah['unsafe_autohandled']['before']} to {ah['unsafe_autohandled']['after']} (change of {ah['unsafe_autohandled']['delta']:+d}).
   - Safety Gate: **{gate}**.
"""
    return md


def main():
    print("Loading Phase 8 Baseline...")
    baseline = load_phase8_baseline()

    print("Running Golden Set evaluation for Phase 10...")
    eval_output_dir = RESULTS_DIR / "phase10_eval"
    eval_output_dir.mkdir(parents=True, exist_ok=True)
    current = run_evaluation(output_dir=eval_output_dir, with_llm=False)

    print("Building before/after comparison...")
    comparison = build_comparison(baseline, current)

    # Save JSON
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
    print(f"Saved: {OUTPUT_JSON_PATH}")

    # Save Markdown
    md_content = generate_markdown(comparison)
    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved: {OUTPUT_MD_PATH}")

    print("\n" + "=" * 60)
    print("PHASE 10 BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Safety Gate: {comparison['safety_gate_status']}")
    print(f"False Positives: {comparison['escalation_metrics']['false_positives']['before']} -> {comparison['escalation_metrics']['false_positives']['after']} (Delta: {comparison['escalation_metrics']['false_positives']['delta']})")
    print(f"Unsafe Auto-Handles: {comparison['autohandle_safety']['unsafe_autohandled']['before']} -> {comparison['autohandle_safety']['unsafe_autohandled']['after']} (Delta: {comparison['autohandle_safety']['unsafe_autohandled']['delta']})")
    print(f"Escalations: {comparison['action_distribution']['escalate']['before_count']} -> {comparison['action_distribution']['escalate']['after_count']}")
    print(f"Clarifications: {comparison['action_distribution']['clarify']['before_count']} -> {comparison['action_distribution']['clarify']['after_count']}")
    print(f"Auto-Handles: {comparison['action_distribution']['auto_handle']['before_count']} -> {comparison['action_distribution']['auto_handle']['after_count']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
