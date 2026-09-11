"""Script to train and evaluate the TF-IDF + Logistic Regression Intent Classifier.

Enforces Golden Set leakage isolation and reports train/validation metrics.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.classifier import IntentClassifier
from src.config import logger
from src.intents import rule_based_intent_labeler
from src.preprocessing import load_golden_set_conversation_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train supervised intent classifier.")
    parser.add_argument(
        "--input-jsonl",
        type=str,
        default=str(backend_dir.parent / "data" / "prepared_cases.jsonl"),
        help="Path to preprocessed historical cases",
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        default=str(backend_dir.parent / "data" / "apple_goldset.csv"),
        help="Path to apple_goldset.csv for strict leakage verification",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(backend_dir / "models" / "intent_classifier.joblib"),
        help="Path to save the trained classifier artifact",
    )
    parser.add_argument(
        "--val-size",
        type=float,
        default=0.2,
        help="Validation split ratio on historical data (default: 0.20)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_jsonl)
    golden_path = Path(args.golden_set)
    output_path = Path(args.output)

    logger.info("=" * 60)
    logger.info("TRAINING INTENT CLASSIFIER (PHASE 4)")
    logger.info("=" * 60)

    if not input_path.exists():
        logger.error("Input cases file not found at %s", input_path)
        sys.exit(1)

    start_time = time.time()

    # 1. Load historical cases
    logger.info("Loading cases from %s...", input_path)
    cases = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    logger.info("Loaded %d historical cases.", len(cases))

    # 2. Strict Golden Set Leakage Verification
    golden_ids = load_golden_set_conversation_ids(golden_path)
    logger.info("Loaded %d conversation IDs from canonical Golden Set: %s", len(golden_ids), golden_path)
    indexed_conv_ids = {c["conversation_id"] for c in cases}
    training_golden_overlap = indexed_conv_ids.intersection(golden_ids)

    # Automated Leakage Assertion
    assert len(training_golden_overlap) == 0, (
        f"Leakage detected: {len(training_golden_overlap)} Golden Set conversation IDs found in training data!"
    )
    logger.info("Leakage check PASSED (assert len(training_golden_overlap) == 0): 0 Golden Set conversations in training data.")

    # 3. Generate Heuristic / Silver Training Labels
    logger.info("=" * 60)
    logger.info("NOTE ON DATA LABELS:")
    logger.info("Training labels on historical cases are generated using deterministic domain heuristic rules.")
    logger.info("These are NOT human labels. The canonical human-reviewed ground truth is exclusively in data/apple_goldset.csv.")
    logger.info("=" * 60)
    texts = [c["customer_message"] for c in cases]
    labels = [rule_based_intent_labeler(t).value for t in texts]

    label_counts = {}
    for l in labels:
        label_counts[l] = label_counts.get(l, 0) + 1
    logger.info("Class distribution across training corpus:")
    for intent_name, cnt in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info("  %-25s: %5d (%.1f%%)", intent_name, cnt, cnt / len(labels) * 100)

    # 4. Train/Validation Split
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts,
        labels,
        test_size=args.val_size,
        random_state=42,
        stratify=labels,
    )
    logger.info("Split into %d train and %d validation examples.", len(train_texts), len(val_texts))

    # 5. Train Classifier
    classifier = IntentClassifier(ngram_range=(1, 2), max_features=30000, C=2.0, max_iter=1000)
    classifier.train(train_texts, train_labels)

    # 6. Evaluate on Validation Split
    logger.info("Evaluating on held-out validation set...")
    val_preds = [classifier.predict(t) for t in val_texts]
    acc = accuracy_score(val_labels, val_preds)
    macro_f1 = f1_score(val_labels, val_preds, average="macro")
    weighted_f1 = f1_score(val_labels, val_preds, average="weighted")

    logger.info("-" * 60)
    logger.info("VALIDATION METRICS:")
    logger.info("  Validation Accuracy: %.4f", acc)
    logger.info("  Macro F1 Score:      %.4f", macro_f1)
    logger.info("  Weighted F1 Score:   %.4f", weighted_f1)
    logger.info("-" * 60)
    logger.info("CLASSIFICATION REPORT:\n%s", classification_report(val_labels, val_preds, digits=4))

    # 7. Persist Artifact
    classifier.save(output_path)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Classifier successfully saved to %s (Size: %.2f MB)", output_path, file_size_mb)

    # 8. Sanity Test Sample Messages
    sample_queries = [
        "My battery is draining completely within 2 hours of use",
        "Forgot my Apple ID password and can't log in",
        "The screen is totally black and touch is unresponsive",
        "Wi-Fi keeps disconnecting every few minutes",
        "Apple music songs stopped playing offline",
        "Can I get a refund for an accidental App Store subscription?",
        "Thank you so much for the quick help today",
    ]

    logger.info("-" * 60)
    logger.info("RUNNING SANITY CLASSIFICATION CHECKS:")
    for query in sample_queries:
        res = classifier.classify(query)
        logger.info("Query: '%s'", query)
        logger.info("  Predicted Intent: %s (Confidence: %.4f)", res.intent.value, res.confidence)
        runner_up = res.top_predictions[1] if len(res.top_predictions) > 1 else None
        if runner_up:
            logger.info("  Runner-Up:        %s (Confidence: %.4f)", runner_up.intent.value, runner_up.confidence)
    logger.info("-" * 60)

    elapsed = time.time() - start_time
    logger.info("Intent classifier training finished in %.2f seconds.", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
