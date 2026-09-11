"""Script to extract support cases from historical conversations and load into MongoDB.

Enforces Golden Set leakage prevention by removing any conversation IDs present in the Golden Set.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

# Add backend directory to sys.path so src imports resolve cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.config import logger
from src.database.mongodb import mongo_manager
from src.database.repositories import SupportCaseRepository
from src.preprocessing import extract_support_cases, load_golden_set_conversation_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract support cases from AppleSupport conversation paths.")
    parser.add_argument(
        "--input",
        type=str,
        default=str(backend_dir.parent / "data" / "apple_full_conversations.csv"),
        help="Path to apple_full_conversations.csv",
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        default=str(backend_dir.parent / "data" / "apple_goldset.csv"),
        help="Path to apple_goldset.csv for leakage prevention",
    )
    parser.add_argument(
        "--output-jsonl",
        type=str,
        default=str(backend_dir.parent / "data" / "prepared_cases.jsonl"),
        help="Path to save processed cases as JSONL for quick retrieval indexing",
    )
    parser.add_argument(
        "--no-mongo",
        action="store_true",
        help="Skip storing cases in MongoDB (only generate local JSONL file)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for bulk insertion into MongoDB",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    golden_path = Path(args.golden_set)
    output_path = Path(args.output_jsonl)

    logger.info("=" * 60)
    logger.info("PREPARING HISTORICAL SUPPORT CASES (PHASE 2)")
    logger.info("=" * 60)
    logger.info("Input conversations: %s", input_path)
    logger.info("Golden set path:     %s", golden_path)
    logger.info("Output JSONL:        %s", output_path)

    if not input_path.exists():
        logger.error("Input file not found at: %s", input_path)
        sys.exit(1)

    start_time = time.time()

    # 1. Load Golden Set IDs for strict leakage prevention
    golden_ids = load_golden_set_conversation_ids(golden_path)
    logger.info("Golden Set conversation count to exclude: %d", len(golden_ids))

    # 2. Read raw conversations
    logger.info("Loading conversation dataset into memory...")
    df = pd.read_csv(input_path)
    logger.info("Loaded %d raw conversation rows across %d unique paths.", len(df), df["conversation_id"].nunique())

    # 3. Extract cases
    logger.info("Extracting customer-response pairs with leakage prevention...")
    cases = extract_support_cases(df, exclude_conversation_ids=golden_ids)
    logger.info("Extracted %d valid support cases.", len(cases))

    # 4. Strict leakage verification check
    extracted_conv_ids = {c.conversation_id for c in cases}
    overlap = extracted_conv_ids.intersection(golden_ids)
    if overlap:
        logger.critical("FATAL: Leakage check failed! %d Golden Set conversations found in corpus: %s", len(overlap), list(overlap)[:5])
        sys.exit(1)
    logger.info("Leakage check PASSED: 0 Golden Set conversations in extracted cases.")

    # 5. Save locally as JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Saving cases to %s...", output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case.model_dump()) + "\n")
    logger.info("Saved %d cases to %s", len(cases), output_path)

    # 6. Store in MongoDB
    if not args.no_mongo:
        logger.info("Connecting to MongoDB to persist support cases...")
        is_healthy, msg = mongo_manager.ping()
        if not is_healthy:
            logger.warning("MongoDB ping failed (%s). Skipping MongoDB persistence.", msg)
        else:
            mongo_manager.init_indexes()
            repo = SupportCaseRepository()
            total_inserted = 0
            batch_size = args.batch_size
            num_cases = len(cases)

            logger.info("Inserting %d cases into MongoDB in batches of %d...", num_cases, batch_size)
            for i in range(0, num_cases, batch_size):
                batch = cases[i : i + batch_size]
                inserted = repo.insert_many_cases(batch, ordered=False)
                total_inserted += inserted
                if (i // batch_size) % 5 == 0 or i + batch_size >= num_cases:
                    logger.info("Progress: %d / %d cases processed...", min(i + batch_size, num_cases), num_cases)

            current_db_count = repo.count_cases()
            logger.info("MongoDB bulk insert complete. Total in DB: %d (newly inserted in this run: %d)", current_db_count, total_inserted)

    elapsed = time.time() - start_time
    logger.info("Support case preparation finished in %.2f seconds.", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
