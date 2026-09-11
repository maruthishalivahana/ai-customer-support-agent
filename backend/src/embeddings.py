"""Dense semantic embedding generation using SentenceTransformers.

Wraps lightweight local embedding models (default: sentence-transformers/all-MiniLM-L6-v2)
to produce normalized dense vectors suitable for cosine similarity via FAISS IndexFlatIP.
"""

from pathlib import Path
from typing import List, Optional, Union
import numpy as np

from src.config import get_settings, logger


class EmbeddingModelWrapper:
    """Wrapper around SentenceTransformer for local deterministic dense embeddings."""

    def __init__(
        self,
        model_name_or_path: Optional[str] = None,
        device: str = "cpu",
    ) -> None:
        """Initialize embedding wrapper.

        Args:
            model_name_or_path: HuggingFace model identifier or local directory.
            device: Device to run embeddings on ('cpu' or 'cuda').
        """
        settings = get_settings()
        self.model_name: str = model_name_or_path or settings.EMBEDDING_MODEL
        self.device: str = device
        self._model = None
        self._dimension: Optional[int] = None

    @property
    def model(self):
        """Lazy load the underlying SentenceTransformer model."""
        if self._model is None:
            self.load()
        return self._model

    def load(self) -> None:
        """Load SentenceTransformer model into memory."""
        if self._model is not None:
            return

        logger.info("Loading sentence embedding model '%s' on %s...", self.model_name, self.device)
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
            # Determine embedding dimension
            test_embedding = self._model.encode("test", convert_to_numpy=True)
            self._dimension = int(test_embedding.shape[-1])
            logger.info(
                "Embedding model '%s' loaded successfully (dimension: %d).",
                self.model_name,
                self._dimension,
            )
        except Exception as exc:
            logger.error("Failed to load embedding model '%s': %s", self.model_name, exc)
            raise

    @property
    def dimension(self) -> int:
        """Embedding dimension (e.g. 384 for all-MiniLM-L6-v2)."""
        if self._dimension is None:
            # Trigger lazy load
            _ = self.model
        return self._dimension  # type: ignore[return-value]

    @staticmethod
    def normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
        """L2-normalize embeddings so that inner product equals cosine similarity.

        Args:
            embeddings: Numpy array of shape (N, D) or (D,).

        Returns:
            L2-normalized float32 numpy array.
        """
        embeddings = np.asarray(embeddings, dtype=np.float32)
        if embeddings.ndim == 1:
            norm = np.linalg.norm(embeddings)
            if norm > 0:
                return (embeddings / norm).astype(np.float32)
            return embeddings.astype(np.float32)

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (embeddings / norms).astype(np.float32)

    def encode_text(self, text: str, normalize: bool = True) -> np.ndarray:
        """Encode a single message into a dense 1D vector.

        Args:
            text: Customer inquiry or message text.
            normalize: Whether to apply L2 normalization (default: True).

        Returns:
            1D float32 numpy array of shape (dimension,).
        """
        if not text or not text.strip():
            # Return zero vector of appropriate dimension
            return np.zeros(self.dimension, dtype=np.float32)

        raw_vec = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return np.asarray(raw_vec, dtype=np.float32)

    def encode_batch(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        normalize: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """Encode a batch of messages into dense 2D vectors.

        Args:
            texts: List of message strings.
            batch_size: Number of messages per batch (default from config).
            normalize: Whether to apply L2 normalization (default: True).
            show_progress_bar: Whether to display progress bar.

        Returns:
            2D float32 numpy array of shape (len(texts), dimension).
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        settings = get_settings()
        effective_batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

        # Replace empty strings with single space to avoid empty tensor issues
        sanitized_texts = [t if (t and t.strip()) else " " for t in texts]

        embeddings = self.model.encode(
            sanitized_texts,
            batch_size=effective_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress_bar,
        )
        return np.asarray(embeddings, dtype=np.float32)


# Global singleton instance
_embedding_instance: Optional[EmbeddingModelWrapper] = None


def get_embedding_model(
    model_name_or_path: Optional[str] = None,
    device: str = "cpu",
) -> EmbeddingModelWrapper:
    """Get or create the global singleton embedding model instance."""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = EmbeddingModelWrapper(
            model_name_or_path=model_name_or_path,
            device=device,
        )
    return _embedding_instance
