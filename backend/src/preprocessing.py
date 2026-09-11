"""Data preprocessing and case extraction pipeline for historical AppleSupport conversations.

Transforms raw conversation paths into structured, grounded support cases suitable
for retrieval while preventing evaluation leakage from the Golden Set.
"""

import html
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.config import logger
from src.schemas import SupportCaseCreate


def clean_text(text: Optional[str], strip_leading_handles: bool = True) -> str:
    """Clean and normalize tweet text.

    Args:
        text: Raw text string.
        strip_leading_handles: If True, removes leading '@AppleSupport' or '@12345' mentions.

    Returns:
        Cleaned, normalized string.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Unescape HTML entities (e.g. &gt; -> >, &amp; -> &)
    cleaned = html.unescape(text)

    # 2. Normalize whitespace and newlines
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 3. Optionally strip leading @mentions
    if strip_leading_handles:
        # Match repeated leading @mentions like "@AppleSupport @115854 "
        cleaned = re.sub(r"^(?:@[\w_]+\s*)+", "", cleaned).strip()

    # 4. Remove unicode directional / zero-width marks
    cleaned = re.sub(r"[\ufe0f\u200b\u200e\u200f]", "", cleaned).strip()

    return cleaned


def load_golden_set_conversation_ids(golden_set_path: Path | str) -> Set[str]:
    """Load conversation IDs from the Golden Set to prevent evaluation leakage.

    Args:
        golden_set_path: Path to apple_goldset.csv

    Returns:
        Set of unique conversation_id strings in the golden set.
    """
    path = Path(golden_set_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Golden set file not found at '{path}'. Cannot proceed without strict leakage prevention."
        )

    df = pd.read_csv(path)
    if "conversation_id" not in df.columns:
        raise ValueError(f"Golden set at '{path}' is missing required 'conversation_id' column.")

    gold_ids = set(df["conversation_id"].dropna().astype(str).str.strip().unique())
    logger.info("Loaded %d unique conversation IDs from Golden Set for exclusion.", len(gold_ids))
    return gold_ids


def extract_support_cases(
    df: pd.DataFrame,
    exclude_conversation_ids: Optional[Set[str]] = None,
    min_text_len: int = 5,
    max_context_turns: int = 3,
) -> List[SupportCaseCreate]:
    """Extract customer problem-response pairs from conversation paths.

    Args:
        df: DataFrame containing conversation paths. Required columns:
            ['conversation_id', 'message_number', 'tweet_id', 'speaker', 'text', 'created_at']
        exclude_conversation_ids: Conversation IDs to exclude (e.g. Golden Set).
        min_text_len: Minimum character length for valid message and response.
        max_context_turns: Maximum preceding turns to retain as conversation context.

    Returns:
        List of validated SupportCaseCreate instances.
    """
    required_cols = {"conversation_id", "message_number", "tweet_id", "speaker", "text"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    # Drop invalid/null rows
    clean_df = df.dropna(subset=["conversation_id", "message_number", "tweet_id", "speaker", "text"]).copy()
    clean_df["conversation_id"] = clean_df["conversation_id"].astype(str).str.strip()
    clean_df["speaker"] = clean_df["speaker"].astype(str).str.strip()
    clean_df["message_number"] = pd.to_numeric(clean_df["message_number"], errors="coerce")
    clean_df = clean_df.dropna(subset=["message_number"])

    # STEP 12: Leakage prevention
    if exclude_conversation_ids:
        initial_count = len(clean_df)
        clean_df = clean_df[~clean_df["conversation_id"].isin(exclude_conversation_ids)]
        excluded_rows = initial_count - len(clean_df)
        logger.info(
            "Leakage Prevention: Excluded %d rows belonging to %d Golden Set conversations.",
            excluded_rows,
            len(exclude_conversation_ids),
        )

    cases: List[SupportCaseCreate] = []
    seen_pairs: Set[tuple] = set()

    # Group by conversation path
    grouped = clean_df.groupby("conversation_id", sort=False)

    for conv_id, group in grouped:
        # Sort sequentially by message_number
        sorted_turns = group.sort_values("message_number").to_dict(orient="records")
        num_turns = len(sorted_turns)

        for i in range(num_turns - 1):
            curr_turn = sorted_turns[i]
            next_turn = sorted_turns[i + 1]

            # Pair: Customer message -> AppleSupport response
            if curr_turn["speaker"] == "Customer" and next_turn["speaker"] == "AppleSupport":
                cust_text = clean_text(curr_turn["text"], strip_leading_handles=True)
                apple_text = clean_text(next_turn["text"], strip_leading_handles=False)

                # Quality checks
                if len(cust_text) < min_text_len or len(apple_text) < min_text_len:
                    continue

                # Deduplicate identical message-response pairs
                pair_key = (cust_text.lower(), apple_text.lower())
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Construct conversation context from up to `max_context_turns` prior turns
                context_turns = sorted_turns[max(0, i - max_context_turns):i]
                context_str = None
                if context_turns:
                    context_str = "\n".join(
                        f"{t['speaker']}: {clean_text(t['text'], strip_leading_handles=False)}"
                        for t in context_turns
                    )

                created_at = str(curr_turn.get("created_at", ""))

                case_id = f"{conv_id}_{curr_turn['tweet_id']}"

                try:
                    case = SupportCaseCreate(
                        case_id=case_id,
                        conversation_id=conv_id,
                        customer_message=cust_text,
                        apple_support_response=apple_text,
                        conversation_context=context_str,
                        created_at=created_at if created_at else None,
                    )
                    cases.append(case)
                except Exception as err:
                    logger.debug("Skipping invalid case %s: %s", case_id, err)
                    continue

    logger.info("Successfully extracted %d support cases from %d conversations.", len(cases), clean_df["conversation_id"].nunique())
    return cases
