"""Evaluation Metrics Calculator.

Computes multi-class intent classification metrics (accuracy, macro/weighted F1,
per-intent breakdown, zero-support classes, confusion matrix) and safety-focused
decision policy metrics (escalation detection, auto-handle precision, unsafe auto-handle rate).
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)

from evaluation.golden_set import AUTHORITATIVE_INTENTS


def calculate_intent_metrics(
    y_true: List[str],
    y_pred: List[str],
) -> Dict[str, Any]:
    """Calculate overall and per-class intent classification metrics across all 12 intents.

    Args:
        y_true: Ground-truth human intent labels.
        y_pred: Predicted intent labels.

    Returns:
        Dictionary containing overall metrics, per-class table, zero-support classes, and confusion matrix.
    """
    labels = AUTHORITATIVE_INTENTS

    # Overall metrics
    acc = float(accuracy_score(y_true, y_pred))
    macro_p = float(precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
    macro_r = float(recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0))

    # Per-class metrics
    p, r, f1, s = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )

    per_intent_metrics = []
    zero_support_classes = []

    for idx, intent_name in enumerate(labels):
        support_cnt = int(s[idx])
        item = {
            "intent": intent_name,
            "precision": round(float(p[idx]), 4),
            "recall": round(float(r[idx]), 4),
            "f1": round(float(f1[idx]), 4),
            "support": support_cnt,
        }
        per_intent_metrics.append(item)
        if support_cnt == 0:
            zero_support_classes.append(intent_name)

    # 12x12 Confusion Matrix
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)

    return {
        "accuracy": round(acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "total_evaluated": len(y_true),
        "zero_support_classes": zero_support_classes,
        "per_intent": per_intent_metrics,
        "confusion_matrix": cm_df,
    }


def calculate_decision_metrics(
    human_escalate: List[str],
    predicted_actions: List[str],
) -> Dict[str, Any]:
    """Calculate safety and decision policy metrics comparing 3-way actions against binary human escalation.

    Evaluation Mappings:
    A. Escalation Detection:
       - Binary target: human_escalate == "YES"
       - Binary prediction: predicted_action == "escalate"
    B. Auto-Handle Safety:
       - Auto-handled: predicted_action == "auto_handle"
       - Unsafe auto-handled: predicted_action == "auto_handle" AND human_escalate == "YES"
       - Safe auto-handled: predicted_action == "auto_handle" AND human_escalate == "NO"
       - Auto-handle Precision = safe_auto_handled / total_auto_handled
       - Unsafe Auto-Handle Rate = unsafe_auto_handled / total_auto_handled
    C. Three-Way Action Distribution:
       - auto_handle, clarify, escalate counts and proportions.

    Args:
        human_escalate: List of 'YES' or 'NO' values from Golden Set.
        predicted_actions: List of 'auto_handle', 'clarify', or 'escalate' actions.

    Returns:
        Dictionary of decision, safety, and distribution metrics.
    """
    total = len(human_escalate)
    if total == 0:
        raise ValueError("Cannot calculate metrics on empty input lists.")

    # 1. Action Distribution
    action_counts = {
        "auto_handle": sum(1 for a in predicted_actions if a == "auto_handle"),
        "clarify": sum(1 for a in predicted_actions if a == "clarify"),
        "escalate": sum(1 for a in predicted_actions if a == "escalate"),
    }
    action_dist = {
        k: {
            "count": v,
            "percentage": round(v / total * 100.0, 2),
        }
        for k, v in action_counts.items()
    }

    # 2. Human Escalation Detection (escalate vs YES)
    y_true_esc = [1 if h == "YES" else 0 for h in human_escalate]
    y_pred_esc = [1 if a == "escalate" else 0 for a in predicted_actions]

    tp = sum(1 for t, p in zip(y_true_esc, y_pred_esc) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true_esc, y_pred_esc) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true_esc, y_pred_esc) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true_esc, y_pred_esc) if t == 0 and p == 0)

    esc_p = float(precision_score(y_true_esc, y_pred_esc, zero_division=0))
    esc_r = float(recall_score(y_true_esc, y_pred_esc, zero_division=0))
    esc_f1 = float(f1_score(y_true_esc, y_pred_esc, zero_division=0))

    # 3. Auto-Handle Safety
    total_autohandle = action_counts["auto_handle"]
    unsafe_autohandle = sum(
        1 for h, a in zip(human_escalate, predicted_actions) if a == "auto_handle" and h == "YES"
    )
    safe_autohandle = total_autohandle - unsafe_autohandle

    if total_autohandle > 0:
        autohandle_precision = round(safe_autohandle / total_autohandle, 4)
        unsafe_autohandle_rate = round(unsafe_autohandle / total_autohandle, 4)
    else:
        autohandle_precision = 0.0
        unsafe_autohandle_rate = 0.0

    return {
        "action_distribution": action_dist,
        "escalation_detection": {
            "precision": round(esc_p, 4),
            "recall": round(esc_r, 4),
            "f1": round(esc_f1, 4),
            "confusion_matrix": {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            },
            "human_escalate_yes_count": sum(y_true_esc),
            "predicted_escalate_count": sum(y_pred_esc),
        },
        "autohandle_safety": {
            "total_autohandled": total_autohandle,
            "safe_autohandled": safe_autohandle,
            "unsafe_autohandled": unsafe_autohandle,
            "autohandle_precision_wrt_no": autohandle_precision,
            "unsafe_autohandle_rate": unsafe_autohandle_rate,
        },
        "three_way_note": (
            "Golden Set provides binary human escalation labels (YES/NO), while the agent provides "
            "three actions (auto_handle, clarify, escalate). 'clarify' is treated as distinct and not "
            "falsely conflated with human escalation."
        ),
    }
