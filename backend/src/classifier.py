"""Supervised Intent Classification Engine for AppleSupport interactions.

Uses TF-IDF + Logistic Regression to classify customer queries into the 12 intents
and returns calibrated class probabilities and confidence scores.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from src.config import logger
from src.preprocessing import clean_text
from src.schemas import ClassificationResponse, Intent, IntentEnum, IntentPredictionItem


class IntentClassifier:
    """TF-IDF + Logistic Regression supervised intent classifier."""

    def __init__(
        self,
        ngram_range: tuple = (1, 2),
        max_features: int = 30000,
        C: float = 2.0,
        max_iter: int = 1000,
    ) -> None:
        self.vectorizer = TfidfVectorizer(
            ngram_range=ngram_range,
            max_features=max_features,
            sublinear_tf=True,
            stop_words="english",
        )
        self.model = LogisticRegression(
            C=C,
            max_iter=max_iter,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )
        self.classes: List[str] = []
        self._is_trained: bool = False

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def train(self, texts: List[str], labels: List[str]) -> Dict[str, float]:
        """Train the TF-IDF vectorizer and Logistic Regression model.

        Args:
            texts: List of customer messages.
            labels: Corresponding intent label strings.

        Returns:
            Dict containing training summary metrics.
        """
        if not texts or not labels:
            raise ValueError("Training texts and labels cannot be empty.")
        if len(texts) != len(labels):
            raise ValueError(f"Length mismatch: {len(texts)} texts vs {len(labels)} labels.")

        logger.info("Training intent classifier on %d examples...", len(texts))
        cleaned_corpus = [clean_text(t, strip_leading_handles=True) for t in texts]

        # 1. Fit vectorizer
        X = self.vectorizer.fit_transform(cleaned_corpus)

        # 2. Fit Logistic Regression
        self.model.fit(X, labels)
        self.classes = list(self.model.classes_)
        self._is_trained = True

        train_acc = float(self.model.score(X, labels))
        logger.info(
            "Classifier training complete. Classes: %d, Vocabulary: %d, Train Accuracy: %.4f",
            len(self.classes),
            len(self.vectorizer.vocabulary_),
            train_acc,
        )
        return {"train_accuracy": round(train_acc, 4), "num_classes": len(self.classes)}

    def predict(self, text: str) -> str:
        """Predict the single most likely intent for a given message."""
        if not self._is_trained:
            raise RuntimeError("IntentClassifier must be trained or loaded before predicting.")

        cleaned = clean_text(text, strip_leading_handles=True)
        if not cleaned:
            return IntentEnum.OTHER_GENERAL.value

        X = self.vectorizer.transform([cleaned])
        return str(self.model.predict(X)[0])

    def predict_proba(self, text: str) -> Dict[str, float]:
        """Return full probability distribution over all 12 intents."""
        if not self._is_trained:
            raise RuntimeError("IntentClassifier must be trained or loaded before predicting.")

        cleaned = clean_text(text, strip_leading_handles=True)
        if not cleaned:
            # Uniform fallback for empty input
            prob = 1.0 / len(self.classes) if self.classes else 1.0
            return {c: round(prob, 4) for c in self.classes}

        X = self.vectorizer.transform([cleaned])
        probs = self.model.predict_proba(X)[0]

        return {cls_name: round(float(prob), 4) for cls_name, prob in zip(self.classes, probs)}

    def classify(self, text: str) -> ClassificationResponse:
        """Return structured classification response matching API schema."""
        proba_dict = self.predict_proba(text)

        # Sort by confidence descending
        sorted_preds = sorted(proba_dict.items(), key=lambda item: item[1], reverse=True)

        top_intent_str, top_conf = sorted_preds[0]

        # Map to IntentEnum safely
        try:
            top_intent = IntentEnum(top_intent_str)
        except ValueError:
            top_intent = IntentEnum.OTHER_GENERAL

        top_items = []
        for intent_str, conf in sorted_preds:
            try:
                enum_val = IntentEnum(intent_str)
                top_items.append(IntentPredictionItem(intent=enum_val, confidence=conf))
            except ValueError:
                continue

        return ClassificationResponse(
            intent=top_intent,
            confidence=top_conf,
            top_predictions=top_items,
        )

    def save(self, filepath: Union[str, Path]) -> None:
        """Save vectorizer, model, and class metadata to disk."""
        if not self._is_trained:
            raise RuntimeError("Cannot save an untrained classifier.")

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "vectorizer": self.vectorizer,
            "model": self.model,
            "classes": self.classes,
        }
        joblib.dump(payload, path, compress=3)
        logger.info("Saved IntentClassifier artifact to %s", path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "IntentClassifier":
        """Load trained classifier from a joblib file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Classifier artifact not found at {path}")

        logger.info("Loading IntentClassifier artifact from %s...", path)
        payload = joblib.load(path)

        classifier = cls()
        classifier.vectorizer = payload["vectorizer"]
        classifier.model = payload["model"]
        classifier.classes = payload["classes"]
        classifier._is_trained = True
        logger.info("IntentClassifier loaded successfully (%d classes).", len(classifier.classes))
        return classifier


# Global singleton instance
_classifier_instance: Optional[IntentClassifier] = None


def get_classifier(artifact_path: Optional[Union[str, Path]] = None) -> Optional[IntentClassifier]:
    """Get or load the global intent classifier instance."""
    global _classifier_instance
    if _classifier_instance is not None:
        return _classifier_instance

    default_path = Path(__file__).resolve().parent.parent / "models" / "intent_classifier.joblib"
    target_path = Path(artifact_path) if artifact_path else default_path

    if target_path.exists():
        try:
            _classifier_instance = IntentClassifier.load(target_path)
            return _classifier_instance
        except Exception as exc:
            logger.warning("Could not load classifier from %s: %s", target_path, exc)

    return None
