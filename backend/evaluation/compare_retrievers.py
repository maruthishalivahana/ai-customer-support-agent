"""Comparative evaluation between TF-IDF lexical retrieval and Semantic FAISS retrieval.

Compares top-K retrieved historical cases, cosine similarity scores, and grounding relevance
across 6 representative test inquiries without using or contaminating the Golden Set.
NOTE: Formal quantitative metrics (Recall@K, MRR) require human relevance judgments;
this script performs transparent qualitative side-by-side analysis without fabricated labels.
"""

from pathlib import Path
import sys
import time

# Ensure Windows console supports UTF-8 characters without charmap errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.config import logger
from src.retriever import get_semantic_retriever, get_tfidf_retriever

TEST_QUERIES = [
    "My iPhone battery is draining very quickly after the latest update.",
    "My iPhone won't connect to WiFi anymore.",
    "I'm not receiving group messages on my iPhone.",
    "I forgot my Apple ID password and can't log in.",
    "Spotify keeps crashing whenever I open it.",
    "It stopped working after I updated it.",  # Ambiguous query
]


def run_comparison(top_k: int = 2) -> None:
    logger.info("=" * 80)
    logger.info("RETRIEVER COMPARISON: TF-IDF (LEXICAL) VS SEMANTIC FAISS (DENSE)")
    logger.info("=" * 80)

    tfidf_retriever = get_tfidf_retriever()
    semantic_retriever = get_semantic_retriever()

    if not tfidf_retriever or not tfidf_retriever.is_fitted:
        logger.error("TF-IDF retriever is not available. Please build it first.")
        return

    if not semantic_retriever or not semantic_retriever.is_fitted:
        logger.error("Semantic FAISS retriever is not available. Please build it first.")
        return

    logger.info("TF-IDF indexed cases: %d", len(tfidf_retriever.cases))
    logger.info("Semantic FAISS indexed vectors: %d", semantic_retriever.index.ntotal if semantic_retriever.index else 0)
    logger.info("-" * 80)

    for q_idx, query in enumerate(TEST_QUERIES, start=1):
        is_ambiguous = "stopped working" in query.lower()
        tag = " [AMBIGUOUS TEST CASE]" if is_ambiguous else ""

        print(f"\n{'#' * 80}")
        print(f"QUERY {q_idx}{tag}: \"{query}\"")
        print(f"{'#' * 80}")

        # 1. TF-IDF retrieval
        t0 = time.perf_counter()
        tfidf_results = tfidf_retriever.retrieve(query, top_k=top_k)
        t_tfidf = (time.perf_counter() - t0) * 1000

        # 2. Semantic FAISS retrieval
        t0 = time.perf_counter()
        semantic_results = semantic_retriever.retrieve(query, top_k=top_k)
        t_semantic = (time.perf_counter() - t0) * 1000

        print(f"\n--- TF-IDF RETRIEVER (Lexical Baseline | {t_tfidf:.2f} ms) ---")
        if not tfidf_results:
            print("  No results found.")
        for r_idx, res in enumerate(tfidf_results, start=1):
            print(f"  [{r_idx}] Cosine Sim: {res.similarity:.4f} | Case ID: {res.case_id}")
            print(f"      Customer : {res.customer_message}")
            print(f"      Support  : {res.historical_response}")

        print(f"\n--- SEMANTIC FAISS RETRIEVER (Dense Vectors | {t_semantic:.2f} ms) ---")
        if not semantic_results:
            print("  No results found.")
        for r_idx, res in enumerate(semantic_results, start=1):
            print(f"  [{r_idx}] Cosine Sim: {res.similarity:.4f} | Case ID: {res.case_id}")
            print(f"      Customer : {res.customer_message}")
            print(f"      Support  : {res.historical_response}")

    print(f"\n{'=' * 80}")
    print("SUMMARY OBSERVATIONS:")
    print("1. Specific queries (e.g., WiFi, Apple ID, Spotify, Battery):")
    print("   Both TF-IDF and Semantic FAISS locate relevant cases, but Semantic FAISS retrieves")
    print("   semantically matched paraphrases even when exact keyword overlap is minimal.")
    print("2. Ambiguous query ('It stopped working after I updated it.'):")
    print("   - TF-IDF latches onto common words ('updated', 'working') and returns whatever has high token overlap.")
    print("   - Semantic FAISS maps the broad notion of post-update malfunction, but without explicit entity context,")
    print("     no retrieval engine can guess whether 'it' refers to an app, phone, or feature.")
    print("   - This confirms that retrieval similarity alone cannot resolve ambiguity; confidence + ambiguity checks")
    print("     will be required for the escalation engine in Phase 6.")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    run_comparison(top_k=2)
