"""Script to build and persist the TF-IDF retrieval index from historical cases.

Enforces leakage prevention and verifies sample queries upon completion.
"""

import argparse
import json
from pathlib import Path
import sys
import time

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.config import logger
from src.database.repositories import SupportCaseRepository
from src.preprocessing import load_golden_set_conversation_ids
from src.retriever import TFIDFRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and save TF-IDF retrieval index.")
    parser.add_argument(
        "--source",
        choices=["file", "mongodb"],
        default="file",
        help="Source for prepared cases ('file' uses prepared_cases.jsonl, 'mongodb' queries DB)",
    )
    parser.add_argument(
        "--input-jsonl",
        type=str,
        default=str(backend_dir.parent / "data" / "prepared_cases.jsonl"),
        help="Path to prepared_cases.jsonl (if source=file)",
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        default=str(backend_dir.parent / "data" / "apple_goldset.csv"),
        help="Path to apple_goldset.csv to verify leakage prevention",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(backend_dir / "models" / "tfidf_retriever.joblib"),
        help="Target filepath to save the fitted retriever artifact",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    golden_path = Path(args.golden_set)

    logger.info("=" * 60)
    logger.info("BUILDING TF-IDF RETRIEVAL INDEX (PHASE 3)")
    logger.info("=" * 60)

    start_time = time.time()

    # 1. Load cases
    cases = []
    if args.source == "file":
        jsonl_path = Path(args.input_jsonl)
        if not jsonl_path.exists():
            logger.error("JSONL file not found at %s. Please run prepare_cases.py first.", jsonl_path)
            sys.exit(1)
        logger.info("Loading cases from JSONL file: %s...", jsonl_path)
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
    else:
        logger.info("Loading cases from MongoDB collection 'support_cases'...")
        repo = SupportCaseRepository()
        cases = repo.fetch_all(limit=100000)

    logger.info("Loaded %d historical support cases for indexing.", len(cases))
    if not cases:
        logger.error("No cases available to index.")
        sys.exit(1)

    # 2. Strict Golden Set Leakage Verification
    golden_ids = load_golden_set_conversation_ids(golden_path)
    indexed_conv_ids = {c["conversation_id"] for c in cases}
    overlap = indexed_conv_ids.intersection(golden_ids)
    if overlap:
        logger.critical("FATAL: Leakage check failed! %d Golden Set conversations found in cases to index: %s", len(overlap), list(overlap)[:5])
        sys.exit(1)
    logger.info("Leakage check PASSED: 0 Golden Set conversations present in corpus.")

    # 3. Fit TF-IDF Retriever
    retriever = TFIDFRetriever(ngram_range=(1, 2), max_features=40000, sublinear_tf=True)
    retriever.fit(cases)

    # 4. Persist Artifact
    retriever.save(output_path)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Retriever successfully saved to %s (Size: %.2f MB)", output_path, file_size_mb)

    # 5. Sanity Test Sample Queries
    sample_queries = [
        "My battery is draining very fast after updating to iOS 11",
        "Forgot my iCloud account password",
        "My iPhone screen is completely black and unresponsive",
    ]

    logger.info("-" * 60)
    logger.info("RUNNING SANITY RETRIEVAL CHECKS:")
    for query in sample_queries:
        results = retriever.retrieve(query, top_k=2)
        logger.info("Query: '%s'", query)
        for rank, res in enumerate(results, start=1):
            logger.info("  [%d] (Sim: %.4f) Cust: %s | Resp: %s", rank, res.similarity, res.customer_message[:60], res.historical_response[:60])
    logger.info("-" * 60)

    elapsed = time.time() - start_time
    logger.info("Index building complete in %.2f seconds.", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
