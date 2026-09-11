"""Baseline Models for Intent Evaluation.

Provides two benchmark baselines to compare against the production SupportDecisionAgent:
1. MajorityClassBaseline: Predicts the single most common class in the training data ('Other / General').
   Strictly NOT fitted on the Golden Set.
2. SimpleTFIDFBaseline: A simple unigram TF-IDF + LogisticRegression classifier trained on
   the historical training cases (data/prepared_cases.jsonl).
"""

import json
import logging
from pathlib import Path
import sys
from typing import List, Optional

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.intents import rule_based_intent_labeler

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_TRAIN_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prepared_cases.jsonl"
DEFAULT_BASELINE_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "baseline_tfidf.joblib"


class MajorityClassBaseline:
    """Majority Class Baseline.

    Predicts the majority class determined strictly from the training dataset
    (data/prepared_cases.jsonl). In the 22,738 AppleSupport training cases,
    'Other / General' comprises 43.75% of cases.
    """

    def __init__(self, majority_intent: str = "Other / General"):
        self.majority_intent = majority_intent

    def predict(self, texts: List[str]) -> List[str]:
        """Predict majority intent for a list of input texts."""
        return [self.majority_intent] * len(texts)

    def predict_one(self, text: str) -> str:
        """Predict majority intent for a single text."""
        return self.majority_intent


class SimpleTFIDFBaseline:
    """Simple TF-IDF Baseline Classifier.

    A basic Unigram TF-IDF Vectorizer (max_features=5000) + LogisticRegression pipeline.
    Trained strictly on historical training data (data/prepared_cases.jsonl) using the same
    historical training labels as the training pipeline.
    Can load from a cached joblib artifact or train on-the-fly.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        train_data_path: Optional[Path] = None,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_BASELINE_MODEL_PATH
        self.train_data_path = Path(train_data_path) if train_data_path else DEFAULT_TRAIN_DATA_PATH
        self.pipeline: Optional[Pipeline] = None

    def load_or_train(self, force_retrain: bool = False) -> None:
        """Load the cached model or train and save a new baseline model."""
        if not force_retrain and self.model_path.exists():
            logger.info(f"Loading cached TF-IDF baseline model from {self.model_path}")
            self.pipeline = joblib.load(self.model_path)
            return

        logger.info(f"Training simple TF-IDF baseline from training cases at {self.train_data_path}")
        self.train()

    def train(self) -> None:
        """Train the simple TF-IDF baseline on historical training data."""
        if not self.train_data_path.exists():
            raise FileNotFoundError(
                f"Training data not found at: {self.train_data_path}. "
                "Cannot train baseline without training data."
            )

        texts = []
        labels = []
        with open(self.train_data_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                cust_msg = record.get("customer_message", "")
                if cust_msg:
                    texts.append(cust_msg)
                    intent = rule_based_intent_labeler(cust_msg).value
                    labels.append(intent)

        if not texts:
            raise ValueError(f"No valid training records found in {self.train_data_path}")

        logger.info(f"Fitting SimpleTFIDFBaseline on {len(texts)} training records...")
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 1), lowercase=True)),
            ("clf", LogisticRegression(max_iter=1000, random_state=42)),
        ])
        pipeline.fit(texts, labels)
        self.pipeline = pipeline

        # Cache artifact
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, self.model_path)
        logger.info(f"Saved baseline TF-IDF model to {self.model_path}")

    def predict(self, texts: List[str]) -> List[str]:
        """Predict intent for a list of input texts."""
        if self.pipeline is None:
            self.load_or_train()
        return list(self.pipeline.predict(texts))

    def predict_one(self, text: str) -> str:
        """Predict intent for a single text."""
        return self.predict([text])[0]
