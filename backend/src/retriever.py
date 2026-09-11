"""Historical customer support case retrieval engine.

Provides an extensible BaseRetriever interface with dual retrieval implementations:
1. TFIDFRetriever — Lexical baseline using TF-IDF n-grams and cosine similarity.
2. SemanticFAISSRetriever — Dense semantic vector search using SentenceTransformer embeddings and FAISS IndexFlatIP.
"""

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import faiss
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import get_settings, logger
from src.embeddings import EmbeddingModelWrapper, get_embedding_model
from src.preprocessing import clean_text
from src.schemas import EvidenceItem


class BaseRetriever(ABC):
    """Abstract interface for historical support case retrievers."""

    @abstractmethod
    def fit(self, cases: List[Dict[str, Any]]) -> None:
        """Index a list of historical support cases."""
        pass

    @abstractmethod
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[EvidenceItem]:
        """Retrieve top-K historically grounded cases matching the customer query."""
        pass

    @abstractmethod
    def save(self, filepath: Union[str, Path]) -> None:
        """Persist index and model artifacts to disk."""
        pass

    @classmethod
    @abstractmethod
    def load(cls, filepath: Union[str, Path]) -> "BaseRetriever":
        """Load persisted index and model artifacts from disk."""
        pass


class TFIDFRetriever(BaseRetriever):
    """Retrieval baseline using TF-IDF n-grams and cosine similarity."""

    def __init__(
        self,
        ngram_range: tuple = (1, 2),
        max_features: int = 40000,
        sublinear_tf: bool = True,
    ) -> None:
        self.vectorizer = TfidfVectorizer(
            ngram_range=ngram_range,
            max_features=max_features,
            sublinear_tf=sublinear_tf,
            stop_words="english",
        )
        self.cases: List[Dict[str, Any]] = []
        self.tfidf_matrix: Optional[Any] = None
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, cases: List[Dict[str, Any]]) -> None:
        """Build TF-IDF vocabulary and matrix over historical customer messages.

        Args:
            cases: List of dictionaries matching the support case structure.
        """
        if not cases:
            raise ValueError("Cannot fit retriever on empty cases list.")

        logger.info("Fitting TF-IDF retriever on %d historical cases...", len(cases))
        corpus = [clean_text(c.get("customer_message", ""), strip_leading_handles=True) for c in cases]

        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.cases = cases
        self._is_fitted = True
        logger.info("Retriever fitted successfully. Vocabulary size: %d", len(self.vectorizer.vocabulary_))

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[EvidenceItem]:
        """Retrieve the top-K most similar historical cases via lexical cosine similarity.

        Args:
            query: Incoming customer query/problem text.
            top_k: Number of cases to retrieve. Defaults to settings.TOP_K_RETRIEVAL.

        Returns:
            List of EvidenceItem ordered by descending similarity score.
        """
        if not self._is_fitted or self.tfidf_matrix is None:
            raise RuntimeError("TFIDFRetriever must be fitted or loaded before calling retrieve().")

        settings = get_settings()
        k = top_k if top_k is not None else settings.TOP_K_RETRIEVAL
        k = max(1, min(k, len(self.cases)))

        cleaned_query = clean_text(query, strip_leading_handles=True)
        if not cleaned_query:
            return []

        # Vectorize incoming query
        query_vec = self.vectorizer.transform([cleaned_query])

        # Compute cosine similarity against all indexed cases
        sim_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Find indices of top-K scores
        if len(sim_scores) <= k:
            top_indices = np.argsort(sim_scores)[::-1]
        else:
            # Use argpartition for O(N) performance on large corpora
            partitioned_indices = np.argpartition(sim_scores, -k)[-k:]
            top_indices = partitioned_indices[np.argsort(sim_scores[partitioned_indices])[::-1]]

        evidence_list: List[EvidenceItem] = []
        for idx in top_indices:
            score = float(sim_scores[idx])
            bounded_score = max(0.0, min(1.0, round(score, 4)))
            case = self.cases[idx]

            evidence_list.append(
                EvidenceItem(
                    case_id=str(case["case_id"]),
                    conversation_id=str(case["conversation_id"]),
                    similarity=bounded_score,
                    customer_message=case["customer_message"],
                    historical_response=case.get("apple_support_response") or case.get("historical_response", ""),
                    conversation_context=case.get("conversation_context"),
                )
            )

        return evidence_list

    def save(self, filepath: Union[str, Path]) -> None:
        """Save vectorizer, tfidf matrix, and cases metadata to a file."""
        if not self._is_fitted:
            raise RuntimeError("Cannot save an unfitted retriever.")

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "vectorizer": self.vectorizer,
            "tfidf_matrix": self.tfidf_matrix,
            "cases": self.cases,
        }
        joblib.dump(payload, path, compress=3)
        logger.info("Saved TFIDFRetriever artifact to %s", path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "TFIDFRetriever":
        """Load retriever from a saved joblib file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Retriever artifact not found at {path}")

        logger.info("Loading TFIDFRetriever artifact from %s...", path)
        payload = joblib.load(path)

        retriever = cls()
        retriever.vectorizer = payload["vectorizer"]
        retriever.tfidf_matrix = payload["tfidf_matrix"]
        retriever.cases = payload["cases"]
        retriever._is_fitted = True
        logger.info("TFIDFRetriever successfully loaded (%d cases indexed).", len(retriever.cases))
        return retriever


class SemanticFAISSRetriever(BaseRetriever):
    """Semantic retrieval engine using dense SentenceTransformer embeddings and FAISS IndexFlatIP.

    Vectors are L2-normalized upon index insertion and query time, ensuring that the FAISS
    inner product corresponds exactly to cosine similarity:
        cosine_similarity(u, v) = (u / ||u||) · (v / ||v||)
    """

    def __init__(
        self,
        embedding_model: Optional[EmbeddingModelWrapper] = None,
    ) -> None:
        self.embedding_model = embedding_model or get_embedding_model()
        self.index: Optional[faiss.IndexFlatIP] = None
        self.cases: List[Dict[str, Any]] = []
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        cases: List[Dict[str, Any]],
        batch_size: Optional[int] = None,
        show_progress_bar: bool = False,
    ) -> None:
        """Build FAISS vector index from historical customer support cases.

        Args:
            cases: List of dictionaries matching the support case structure.
            batch_size: Batch size for dense embedding inference.
            show_progress_bar: Whether to display an encoding progress bar.
        """
        if not cases:
            raise ValueError("Cannot fit retriever on empty cases list.")

        logger.info(
            "Fitting Semantic FAISS retriever on %d historical cases using model '%s'...",
            len(cases),
            self.embedding_model.model_name,
        )

        corpus = [clean_text(c.get("customer_message", ""), strip_leading_handles=True) for c in cases]

        # Batch encode with L2 normalization
        embeddings = self.embedding_model.encode_batch(
            corpus,
            batch_size=batch_size,
            normalize=True,
            show_progress_bar=show_progress_bar,
        )
        embeddings = np.asarray(embeddings, dtype=np.float32)

        # Build FAISS IndexFlatIP for exact inner product (= cosine similarity for normalized vectors)
        dimension = self.embedding_model.dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

        # Store metadata mapping 1:1 with row index
        self.cases = [
            {
                "case_id": str(c["case_id"]),
                "conversation_id": str(c["conversation_id"]),
                "customer_message": c["customer_message"],
                "apple_support_response": c.get("apple_support_response") or c.get("historical_response", ""),
                "conversation_context": c.get("conversation_context"),
            }
            for c in cases
        ]
        self._is_fitted = True
        logger.info("SemanticFAISSRetriever fitted successfully. Total indexed vectors: %d", self.index.ntotal)

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[EvidenceItem]:
        """Retrieve top-K most semantically similar historical cases via dense FAISS search.

        Args:
            query: Incoming customer query/problem text.
            top_k: Number of cases to retrieve. Defaults to settings.TOP_K_RETRIEVAL.

        Returns:
            List of EvidenceItem ordered by descending cosine similarity score.
        """
        if not self._is_fitted or self.index is None:
            raise RuntimeError("SemanticFAISSRetriever must be fitted or loaded before calling retrieve().")

        settings = get_settings()
        k = top_k if top_k is not None else settings.TOP_K_RETRIEVAL
        k = max(1, min(k, self.index.ntotal))

        cleaned_query = clean_text(query, strip_leading_handles=True)
        if not cleaned_query:
            return []

        # Encode query into normalized vector
        query_vec = self.embedding_model.encode_text(cleaned_query, normalize=True)
        query_vec = query_vec.reshape(1, -1).astype(np.float32)

        # Search FAISS index
        distances, indices = self.index.search(query_vec, k)

        evidence_list: List[EvidenceItem] = []
        for sim_score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.cases):
                continue

            # In IndexFlatIP with normalized vectors, inner product == cosine similarity.
            # Convert float32 to standard float and bound to [0.0, 1.0]
            score_val = float(sim_score)
            bounded_score = max(0.0, min(1.0, round(score_val, 4)))
            case = self.cases[idx]

            evidence_list.append(
                EvidenceItem(
                    case_id=case["case_id"],
                    conversation_id=case["conversation_id"],
                    similarity=bounded_score,
                    customer_message=case["customer_message"],
                    historical_response=case["apple_support_response"],
                    conversation_context=case.get("conversation_context"),
                )
            )

        return evidence_list

    def save(
        self,
        filepath: Union[str, Path],
        metadata_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Save FAISS binary vector index and accompanying JSON metadata to disk.

        Args:
            filepath: Target file path for the FAISS index (.index).
            metadata_path: Optional explicit path for the JSON metadata.
                           Defaults to '<filepath>.metadata.json'.
        """
        if not self._is_fitted or self.index is None:
            raise RuntimeError("Cannot save an unfitted SemanticFAISSRetriever.")

        index_path = Path(filepath)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        meta_path = Path(metadata_path) if metadata_path else index_path.with_name(f"{index_path.stem}_metadata.json")

        # 1. Save FAISS binary index
        faiss.write_index(self.index, str(index_path))

        # 2. Save metadata and embedding model configuration
        meta_payload = {
            "embedding_model": self.embedding_model.model_name,
            "dimension": self.embedding_model.dimension,
            "num_cases": len(self.cases),
            "index_type": "IndexFlatIP",
            "similarity_metric": "cosine (normalized inner product)",
            "cases": self.cases,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_payload, f, indent=2)

        logger.info(
            "Saved SemanticFAISSRetriever artifacts to %s and %s (%d cases)",
            index_path,
            meta_path,
            len(self.cases),
        )

    @classmethod
    def load(
        cls,
        filepath: Union[str, Path],
        metadata_path: Optional[Union[str, Path]] = None,
        embedding_model: Optional[EmbeddingModelWrapper] = None,
    ) -> "SemanticFAISSRetriever":
        """Load FAISS binary vector index and JSON metadata from disk.

        Args:
            filepath: Path to the FAISS binary index file (.index).
            metadata_path: Path to the metadata JSON file. If omitted, attempts to locate
                           the companion file next to the index.
            embedding_model: Optional preloaded EmbeddingModelWrapper.
        """
        index_path = Path(filepath)
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index file not found at {index_path}")

        # Locate metadata JSON
        candidates = []
        if metadata_path:
            candidates.append(Path(metadata_path))
        candidates.extend([
            index_path.with_name(f"{index_path.stem}_metadata.json"),
            index_path.with_suffix(".json"),
            index_path.parent / "semantic_faiss_metadata.json",
        ])

        resolved_meta_path = None
        for candidate in candidates:
            if candidate.exists():
                resolved_meta_path = candidate
                break

        if not resolved_meta_path:
            raise FileNotFoundError(f"Metadata JSON file not found for FAISS index at {index_path}")

        logger.info("Loading SemanticFAISSRetriever from %s and %s...", index_path, resolved_meta_path)
        index = faiss.read_index(str(index_path))

        with open(resolved_meta_path, "r", encoding="utf-8") as f:
            meta_payload = json.load(f)

        cases = meta_payload["cases"]
        if index.ntotal != len(cases):
            raise ValueError(
                f"Mismatch between FAISS index vector count ({index.ntotal}) "
                f"and metadata case count ({len(cases)})."
            )

        model_name = meta_payload.get("embedding_model")
        emb_wrapper = embedding_model or get_embedding_model(model_name_or_path=model_name)

        retriever = cls(embedding_model=emb_wrapper)
        retriever.index = index
        retriever.cases = cases
        retriever._is_fitted = True
        logger.info("SemanticFAISSRetriever loaded successfully (%d vectors).", index.ntotal)
        return retriever


# Global singleton instances
_tfidf_instance: Optional[TFIDFRetriever] = None
_semantic_instance: Optional[SemanticFAISSRetriever] = None


def get_tfidf_retriever(artifact_path: Optional[Union[str, Path]] = None) -> Optional[TFIDFRetriever]:
    """Get or load the global TF-IDF retriever instance."""
    global _tfidf_instance
    if _tfidf_instance is not None:
        return _tfidf_instance

    default_path = Path(__file__).resolve().parent.parent / "models" / "tfidf_retriever.joblib"
    target_path = Path(artifact_path) if artifact_path else default_path

    if target_path.exists():
        try:
            _tfidf_instance = TFIDFRetriever.load(target_path)
            return _tfidf_instance
        except Exception as exc:
            logger.warning("Could not load TF-IDF retriever from %s: %s", target_path, exc)

    return None


def get_semantic_retriever(
    index_path: Optional[Union[str, Path]] = None,
    metadata_path: Optional[Union[str, Path]] = None,
    embedding_model: Optional[EmbeddingModelWrapper] = None,
) -> Optional[SemanticFAISSRetriever]:
    """Get or load the global Semantic FAISS retriever instance."""
    global _semantic_instance
    if _semantic_instance is not None:
        return _semantic_instance

    settings = get_settings()
    target_index = Path(index_path) if index_path else settings.FAISS_INDEX_PATH
    target_meta = Path(metadata_path) if metadata_path else settings.FAISS_METADATA_PATH

    if target_index.exists():
        try:
            _semantic_instance = SemanticFAISSRetriever.load(
                filepath=target_index,
                metadata_path=target_meta if target_meta.exists() else None,
                embedding_model=embedding_model,
            )
            return _semantic_instance
        except Exception as exc:
            logger.warning("Could not load Semantic FAISS retriever from %s: %s", target_index, exc)

    return None


def get_retriever(
    retriever_type: Optional[str] = None,
    artifact_path: Optional[Union[str, Path]] = None,
) -> Optional[BaseRetriever]:
    """Get retriever based on engine type ('semantic' or 'tfidf').

    Defaults to settings.RETRIEVER_TYPE. Falls back to available loaded retriever if possible.
    """
    settings = get_settings()
    target_type = (retriever_type or settings.RETRIEVER_TYPE).lower()

    if target_type == "semantic":
        semantic = get_semantic_retriever(index_path=artifact_path)
        if semantic is not None:
            return semantic
        # Fallback to TF-IDF if semantic not yet built
        return get_tfidf_retriever()
    elif target_type == "tfidf":
        tfidf = get_tfidf_retriever(artifact_path=artifact_path)
        if tfidf is not None:
            return tfidf
        return get_semantic_retriever()

    # Fallback to whichever is available
    return get_semantic_retriever() or get_tfidf_retriever()
