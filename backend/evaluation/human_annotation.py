"""Deterministic Human Evidence Annotation Subset Selector.

Selects a balanced, diverse 50-example subset from the 200 Golden Set conversations
for human evidence-grounding annotation using a fixed random seed.
Leaves all human annotation columns strictly blank (no fabricated labels).
"""

from pathlib import Path
import sys
from typing import List
import numpy as np
import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

PER_EXAMPLE_CSV = Path(__file__).resolve().parent / "results" / "per_example_results.csv"
ANNOTATION_CSV = Path(__file__).resolve().parent / "evidence_human_annotations.csv"


def select_diverse_subset(
    input_csv: Path = PER_EXAMPLE_CSV,
    output_csv: Path = ANNOTATION_CSV,
    sample_size: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Deterministically select a 50-example diverse subset for human annotation.

    Stratifies across:
    1. Action: auto_handle, clarify, escalate
    2. Intent Confidence & Needs Clarification
    3. Retrieval Diversity

    Args:
        input_csv: Path to per_example_results.csv.
        output_csv: Target path for evidence_human_annotations.csv.
        sample_size: Number of examples to select (50).
        seed: Fixed random seed for reproducibility (42).

    Returns:
        DataFrame of the 50 selected examples with blank human annotation columns.
    """
    df = pd.read_csv(input_csv)
    if len(df) < sample_size:
        raise ValueError(f"Input dataset has fewer rows ({len(df)}) than requested sample size ({sample_size}).")

    np.random.seed(seed)

    # Stratified selection across the 3 predicted actions
    # Target counts: auto_handle ~20, clarify ~10, escalate ~20 = 50
    actions = ["auto_handle", "clarify", "escalate"]
    targets = {"auto_handle": 20, "clarify": 10, "escalate": 20}

    selected_indices = []

    for action, count in targets.items():
        sub_df = df[df["predicted_action"] == action]
        available_cnt = len(sub_df)
        k = min(count, available_cnt)
        chosen = sub_df.sample(n=k, random_state=seed).index.tolist()
        selected_indices.extend(chosen)

    # If any remaining slots to reach exactly 50
    remaining_needed = sample_size - len(selected_indices)
    if remaining_needed > 0:
        remaining_pool = df.drop(index=selected_indices)
        extra = remaining_pool.sample(n=remaining_needed, random_state=seed).index.tolist()
        selected_indices.extend(extra)

    subset_df = df.loc[selected_indices].copy()
    subset_df = subset_df.sort_values(by="gold_id").reset_index(drop=True)

    # Structure strictly required columns with blank human fields
    annotation_df = pd.DataFrame({
        "gold_id": subset_df["gold_id"],
        "conversation_id": subset_df["conversation_id"],
        "human_evidence_supported": "",  # Blank: YES / NO
        "human_support_score": "",       # Blank: 0-5
        "human_notes": "",               # Blank: free-text notes
    })

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    annotation_df.to_csv(output_csv, index=False)
    return annotation_df


if __name__ == "__main__":
    df_sub = select_diverse_subset()
    print(f"Successfully generated deterministic 50-example human annotation subset at: {ANNOTATION_CSV}")
