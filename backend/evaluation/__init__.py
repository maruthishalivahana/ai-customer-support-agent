"""Evaluation harness package for Hiver AI Customer Support Agent.

Provides validation, benchmarking, baselines, and reporting on the Golden Set.
"""

from evaluation.baselines import MajorityClassBaseline, SimpleTFIDFBaseline
from evaluation.golden_set import (
    AUTHORITATIVE_INTENTS,
    REQUIRED_COLUMNS,
    load_and_validate_golden_set,
    reconstruct_conversation,
)
from evaluation.metrics import calculate_decision_metrics, calculate_intent_metrics
from evaluation.report import print_terminal_report, save_evaluation_artifacts

__all__ = [
    "AUTHORITATIVE_INTENTS",
    "REQUIRED_COLUMNS",
    "load_and_validate_golden_set",
    "reconstruct_conversation",
    "calculate_intent_metrics",
    "calculate_decision_metrics",
    "MajorityClassBaseline",
    "SimpleTFIDFBaseline",
    "save_evaluation_artifacts",
    "print_terminal_report",
]
