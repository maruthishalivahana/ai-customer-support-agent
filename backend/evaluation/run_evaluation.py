"""Golden Set Evaluation Runner.

Orchestrates the complete Phase 8 evaluation harness:
1. Validates the canonical 200-sample Golden Set (data/apple_goldset.csv).
2. Reconstructs multi-turn dialogue contexts.
3. Evaluates the production SupportDecisionAgent (intent, decision action, safety).
4. Evaluates the Majority Class Baseline and Simple TF-IDF Baseline.
5. Computes multi-class intent metrics, confusion matrix, and safety metrics.
6. Saves 5 machine-readable evaluation artifacts into backend/evaluation/results/.
7. Displays a clean, comprehensive terminal benchmark report.
"""

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

import pandas as pd

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.agent import SupportDecisionAgent, get_support_agent
from src.conversation import ConversationState
from src.generator import SupportResponseGenerator
from src.schemas import IntentEnum, MessageRole, SupportAction
from evaluation.baselines import MajorityClassBaseline, SimpleTFIDFBaseline
from evaluation.golden_set import (
    AUTHORITATIVE_INTENTS,
    load_and_validate_golden_set,
    reconstruct_conversation,
)
from evaluation.metrics import calculate_decision_metrics, calculate_intent_metrics
from evaluation.report import print_terminal_report, save_evaluation_artifacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluation.run")

DEFAULT_GOLDSET_PATH = backend_dir.parent / "data" / "apple_goldset.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def run_evaluation(
    goldset_path: Path = DEFAULT_GOLDSET_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    with_llm: bool = False,
    retrain_baseline: bool = False,
) -> Dict[str, Any]:
    """Execute the full evaluation benchmark.

    Args:
        goldset_path: Path to canonical apple_goldset.csv.
        output_dir: Directory to store output CSVs and JSON.
        with_llm: If True, invoke OpenRouter LLM for text generation. If False (default),
                 use deterministic fast generator for speed and safety.
        retrain_baseline: If True, force re-fitting the Simple TF-IDF baseline model.

    Returns:
        Evaluation summary dict.
    """
    goldset_path = Path(goldset_path).resolve()
    output_dir = Path(output_dir).resolve()

    logger.info(f"Step 1: Loading and validating Golden Set from: {goldset_path}")
    df_gold = load_and_validate_golden_set(goldset_path)
    logger.info(f"Validation successful! Loaded exactly {len(df_gold)} Golden Set examples.")

    # Step 2: Initialize Baselines
    logger.info("Step 2: Initializing evaluation baselines...")
    majority_baseline = MajorityClassBaseline(majority_intent="Other / General")
    tfidf_baseline = SimpleTFIDFBaseline()
    tfidf_baseline.load_or_train(force_retrain=retrain_baseline)

    class DeterministicResponseGenerator(SupportResponseGenerator):
        @property
        def client(self):
            return None

    if with_llm:
        generator = SupportResponseGenerator()
    else:
        # Use deterministic generator for fast, quota-free evaluation
        generator = DeterministicResponseGenerator()

    agent = SupportDecisionAgent(generator=generator)

    # Step 4: Run Benchmarking Loop
    logger.info("Step 4: Benchmarking 200 Golden Set conversations through agent and baselines...")
    per_example_rows: List[Dict[str, Any]] = []

    y_true_intent: List[str] = []
    y_pred_agent_intent: List[str] = []
    y_pred_majority_intent: List[str] = []
    y_pred_tfidf_intent: List[str] = []

    y_true_escalate: List[str] = []
    y_pred_agent_action: List[str] = []

    for idx, row in df_gold.iterrows():
        gold_id = int(row["gold_id"])
        conv_id = str(row["conversation_id"])
        human_intent = str(row["human_intent"]).strip()
        human_esc = str(row["human_escalate"]).strip()

        # Reconstruct dialogue turns
        messages = reconstruct_conversation(row)
        conv_state = ConversationState(conversation_id=conv_id, messages=messages)

        latest_cust_msg = conv_state.latest_customer_message.text.strip()
        effective_query = conv_state.get_effective_query()

        # 1. Agent Evaluation
        agent_resp = agent.process(conv_state)
        pred_intent = (
            agent_resp.intent.value
            if isinstance(agent_resp.intent, IntentEnum)
            else str(agent_resp.intent)
        )
        pred_action = (
            agent_resp.action.value
            if isinstance(agent_resp.action, SupportAction)
            else str(agent_resp.action)
        )
        intent_conf = float(agent_resp.intent_confidence)

        # 2. Baseline Predictions
        maj_pred = majority_baseline.predict_one(latest_cust_msg)
        tfidf_pred = tfidf_baseline.predict_one(latest_cust_msg)

        # Store for batch metrics
        y_true_intent.append(human_intent)
        y_pred_agent_intent.append(pred_intent)
        y_pred_majority_intent.append(maj_pred)
        y_pred_tfidf_intent.append(tfidf_pred)

        y_true_escalate.append(human_esc)
        y_pred_agent_action.append(pred_action)

        # Audit flags
        intent_correct = int(pred_intent == human_intent)
        escalate_match = int(
            (pred_action == "escalate" and human_esc == "YES")
            or (pred_action != "escalate" and human_esc == "NO")
        )
        unsafe_autohandle = int(pred_action == "auto_handle" and human_esc == "YES")

        per_example_rows.append({
            "gold_id": gold_id,
            "conversation_id": conv_id,
            "latest_customer_message": latest_cust_msg,
            "human_intent": human_intent,
            "predicted_intent": pred_intent,
            "intent_correct": intent_correct,
            "intent_confidence": round(intent_conf, 4),
            "human_escalate": human_esc,
            "predicted_action": pred_action,
            "escalate_match": escalate_match,
            "unsafe_autohandle": unsafe_autohandle,
            "needs_clarification": int(agent_resp.signals.ambiguous or pred_action == "clarify"),
            "retrieved_evidence_count": len(agent_resp.evidence),
            "majority_pred_intent": maj_pred,
            "tfidf_pred_intent": tfidf_pred,
        })

    # Step 5: Compute Metrics
    logger.info("Step 5: Calculating Intent Classification & Decision Policy Metrics...")
    agent_intent_metrics = calculate_intent_metrics(y_true_intent, y_pred_agent_intent)
    maj_intent_metrics = calculate_intent_metrics(y_true_intent, y_pred_majority_intent)
    tfidf_intent_metrics = calculate_intent_metrics(y_true_intent, y_pred_tfidf_intent)

    decision_metrics = calculate_decision_metrics(y_true_escalate, y_pred_agent_action)

    # Build Baseline Comparison Table
    baseline_comparison_rows = [
        {
            "Model": "Production Support Agent",
            "Accuracy": agent_intent_metrics["accuracy"],
            "Macro Precision": agent_intent_metrics["macro_precision"],
            "Macro Recall": agent_intent_metrics["macro_recall"],
            "Macro F1": agent_intent_metrics["macro_f1"],
            "Weighted F1": agent_intent_metrics["weighted_f1"],
        },
        {
            "Model": "Simple TF-IDF Baseline",
            "Accuracy": tfidf_intent_metrics["accuracy"],
            "Macro Precision": tfidf_intent_metrics["macro_precision"],
            "Macro Recall": tfidf_intent_metrics["macro_recall"],
            "Macro F1": tfidf_intent_metrics["macro_f1"],
            "Weighted F1": tfidf_intent_metrics["weighted_f1"],
        },
        {
            "Model": "Majority Class Baseline ('Other / General')",
            "Accuracy": maj_intent_metrics["accuracy"],
            "Macro Precision": maj_intent_metrics["macro_precision"],
            "Macro Recall": maj_intent_metrics["macro_recall"],
            "Macro F1": maj_intent_metrics["macro_f1"],
            "Weighted F1": maj_intent_metrics["weighted_f1"],
        },
    ]
    baseline_df = pd.DataFrame(baseline_comparison_rows)
    intent_df = pd.DataFrame(agent_intent_metrics["per_intent"])
    cm_df = agent_intent_metrics["confusion_matrix"]

    # Step 6: Assemble Full Evaluation Summary
    dataset_intent_counts = df_gold["human_intent"].value_counts().to_dict()
    summary = {
        "metadata": {
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "classifier_type": "TF-IDF + Logistic Regression",
            "retriever_type": "SentenceTransformers (all-MiniLM-L6-v2) + FAISS",
            "decision_policy": "Conversation-aware 3-way policy (auto_handle, clarify, escalate)",
            "with_llm_generation": with_llm,
        },
        "dataset": {
            "source_file": "data/apple_goldset.csv",
            "total_examples": len(df_gold),
            "unique_conversations": df_gold["conversation_id"].nunique(),
            "escalate_yes_count": int((df_gold["human_escalate"] == "YES").sum()),
            "escalate_no_count": int((df_gold["human_escalate"] == "NO").sum()),
            "intent_distribution": dataset_intent_counts,
        },
        "agent_intent_metrics": agent_intent_metrics,
        "baseline_comparison": baseline_comparison_rows,
        "decision_and_safety_metrics": decision_metrics,
    }

    # Step 7: Save Evaluation Artifacts
    logger.info(f"Step 6: Saving evaluation artifacts to {output_dir}...")
    saved_files = save_evaluation_artifacts(
        evaluation_summary=summary,
        per_example_rows=per_example_rows,
        intent_metrics_table=agent_intent_metrics["per_intent"],
        confusion_matrix_df=cm_df,
        baseline_comparison_df=baseline_df,
        output_dir=output_dir,
    )
    for name, p in saved_files.items():
        logger.info(f"  - Saved {name}: {p}")

    # Step 8: Terminal Report
    print_terminal_report(summary, baseline_df, intent_df)

    return summary


def main() -> None:
    """CLI entry point for running the evaluation harness."""
    parser = argparse.ArgumentParser(
        description="Run Phase 8 Golden Set Evaluation Harness on AppleSupport Agent."
    )
    parser.add_argument(
        "--goldset",
        type=Path,
        default=DEFAULT_GOLDSET_PATH,
        help="Path to canonical apple_goldset.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save evaluation artifacts",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        default=False,
        help="Enable full OpenRouter LLM response generation during evaluation (default: deterministic)",
    )
    parser.add_argument(
        "--retrain-baseline",
        action="store_true",
        default=False,
        help="Force retrain the Simple TF-IDF baseline model",
    )

    args = parser.parse_args()
    run_evaluation(
        goldset_path=args.goldset,
        output_dir=args.output_dir,
        with_llm=args.with_llm,
        retrain_baseline=args.retrain_baseline,
    )


if __name__ == "__main__":
    main()
