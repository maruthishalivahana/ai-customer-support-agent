"""Script to build and persist the FAISS dense semantic retrieval index.

Indexes historical customer support cases from data/prepared_cases.jsonl into a FAISS
IndexFlatIP vector index using local SentenceTransformer embeddings.
Enforces strict zero-leakage validation against the canonical Golden Set (data/apple_goldset.csv).
"""

import argparse
import json
from pathlib import Path
import sys
import time

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.config import get_settings, logger
from src.embeddings import get_embedding_model
from src.preprocessing import load_golden_set_conversation_ids
from src.retriever import SemanticFAISSRetriever


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build and save FAISS semantic retrieval index.")
    parser.add_argument(
        "--input-jsonl",
        type=str,
        default=str(backend_dir.parent / "data" / "prepared_cases.jsonl"),
        help="Path to prepared_cases.jsonl source of truth",
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        default=str(backend_dir.parent / "data" / "apple_goldset.csv"),
        help="Path to canonical apple_goldset.csv for leakage verification",
    )
    parser.add_argument(
        "--output-index",
        type=str,
        default=str(settings.FAISS_INDEX_PATH),
        help="Destination path for FAISS index (.index)",
    )
    parser.add_argument(
        "--output-metadata",
        type=str,
        default=str(settings.FAISS_METADATA_PATH),
        help="Destination path for metadata JSON file",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=settings.EMBEDDING_MODEL,
        help="SentenceTransformer model name or local path",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.EMBEDDING_BATCH_SIZE,
        help="Inference batch size for embedding generation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_jsonl)
    golden_path = Path(args.golden_set)
    output_index_path = Path(args.output_index)
    output_meta_path = Path(args.output_metadata)

    logger.info("=" * 70)
    logger.info("PHASE 5: BUILDING SEMANTIC FAISS RETRIEVAL INDEX")
    logger.info("=" * 70)

    start_time = time.time()

    # 1. Load prepared historical support cases
    if not input_path.exists():
        logger.critical("Source file not found at %s. Please run prepare_cases.py first.", input_path)
        sys.exit(1)

    logger.info("Loading prepared cases from: %s", input_path)
    cases = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if line_str:
                cases.append(json.loads(line_str))

    num_cases = len(cases)
    logger.info("Loaded %d historical support cases.", num_cases)
    if num_cases == 0:
        logger.critical("Input dataset is empty. Cannot construct index.")
        sys.exit(1)

    # 2. Strict Golden Set Leakage Verification (Pre-Build)
    if not golden_path.exists():
        logger.critical("Golden set not found at %s. Cannot verify leakage.", golden_path)
        sys.exit(1)

    golden_ids = load_golden_set_conversation_ids(golden_path)
    logger.info("Loaded %d canonical Golden Set conversation IDs.", len(golden_ids))

    indexed_conv_ids = {str(c["conversation_id"]) for c in cases}
    overlap = golden_ids.intersection(indexed_conv_ids)
    leakage_count = len(overlap)

    if leakage_count > 0:
        logger.critical(
            "FATAL: Golden Set leakage detected! %d conversations overlap: %s",
            leakage_count,
            list(overlap)[:5],
        )
        sys.exit(1)

    assert leakage_count == 0, f"Expected 0 leakage, found {leakage_count}"
    logger.info("PRE-BUILD LEAKAGE CHECK PASSED: 0 Golden Set conversations in corpus.")

    # 3. Initialize Embedding Model
    logger.info("Initializing SentenceTransformer: '%s'...", args.model_name)
    emb_model = get_embedding_model(model_name_or_path=args.model_name, device="cpu")
    emb_dim = emb_model.dimension
    logger.info("Embedding dimension: %d", emb_dim)

    # 4. Fit Semantic FAISS Retriever (Batch Encoding + IndexFlatIP)
    logger.info("Building FAISS index with batch_size=%d...", args.batch_size)
    retriever = SemanticFAISSRetriever(embedding_model=emb_model)
    fit_start = time.time()
    retriever.fit(cases, batch_size=args.batch_size, show_progress_bar=True)
    fit_elapsed = time.time() - fit_start
    logger.info("Embedding generation and FAISS indexing completed in %.2f seconds.", fit_elapsed)

    # 5. Persist Index and Metadata
    logger.info("Persisting FAISS index to %s...", output_index_path)
    logger.info("Persisting metadata to %s...", output_meta_path)
    retriever.save(filepath=output_index_path, metadata_path=output_meta_path)

    # 6. Post-Build Verification: Count & Leakage Check
    loaded_retriever = SemanticFAISSRetriever.load(
        filepath=output_index_path,
        metadata_path=output_meta_path,
        embedding_model=emb_model,
    )

    loaded_vector_count = loaded_retriever.index.ntotal
    loaded_case_count = len(loaded_retriever.cases)
    logger.info("Verifying index consistency: %d vectors vs %d metadata records", loaded_vector_count, loaded_case_count)

    assert loaded_vector_count == num_cases, (
        f"Vector count mismatch: expected {num_cases}, got {loaded_vector_count}"
    )
    assert loaded_case_count == num_cases, (
        f"Metadata count mismatch: expected {num_cases}, got {loaded_case_count}"
    )

    loaded_conv_ids = {str(c["conversation_id"]) for c in loaded_retriever.cases}
    post_overlap = golden_ids.intersection(loaded_conv_ids)
    assert len(post_overlap) == 0, f"Post-build leakage detected: {len(post_overlap)}"
    logger.info("POST-BUILD LEAKAGE CHECK PASSED: 0 Golden Set conversations in index.")

    total_time = time.time() - start_time
    index_size_mb = output_index_path.stat().st_size / (1024 * 1024)
    meta_size_mb = output_meta_path.stat().st_size / (1024 * 1024)

    # 7. Print Build Statistics
    logger.info("=" * 70)
    logger.info("PHASE 5 BUILD STATISTICS:")
    logger.info("  - Total Prepared Cases : %d", num_cases)
    logger.info("  - Indexed Vectors      : %d", loaded_vector_count)
    logger.info("  - Metadata Records     : %d", loaded_case_count)
    logger.info("  - Embedding Model      : %s", args.model_name)
    logger.info("  - Embedding Dimension  : %d", emb_dim)
    logger.info("  - Batch Size           : %d", args.batch_size)
    logger.info("  - Index Type           : IndexFlatIP (Exact Cosine via Inner Product)")
    logger.info("  - Total Build Time     : %.2f seconds", total_time)
    logger.info("  - Index File Size      : %.2f MB (%s)", index_size_mb, output_index_path.name)
    logger.info("  - Metadata File Size   : %.2f MB (%s)", meta_size_mb, output_meta_path.name)
    logger.info("  - Golden Set Overlap   : 0 (Strict 0-leakage maintained)")
    logger.info("=" * 70)

    # 8. Sanity Retrieval Check
    sample_queries = [
        "My iPhone battery is draining very quickly after the latest update.",
        "It stopped working after I updated it.",
    ]
    logger.info("SANITY RETRIEVAL CHECKS:")
    for query in sample_queries:
        logger.info("-" * 50)
        logger.info("Query: '%s'", query)
        results = loaded_retriever.retrieve(query, top_k=2)
        for rank, res in enumerate(results, start=1):
            logger.info(
                "  [%d] Similarity: %.4f | Case: %s | Message: %s | Reply: %s",
                rank,
                res.similarity,
                res.case_id,
                res.customer_message[:55],
                res.historical_response[:55],
            )
    logger.info("=" * 70)
    logger.info("Semantic index construction successfully completed.")


if __name__ == "__main__":
    main()
