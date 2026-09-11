"""Golden Set Loader and Validator.

Enforces strict schema validation, integrity checks, and conversation reconstruction
on the canonical human-reviewed Golden Set (data/apple_goldset.csv).
The Golden Set is strictly READ-ONLY evaluation data.
"""

from pathlib import Path
from typing import List
import pandas as pd

from src.schemas import IntentEnum, MessageItem, MessageRole

# The 12 Authoritative Intents
AUTHORITATIVE_INTENTS = [intent.value for intent in IntentEnum]

REQUIRED_COLUMNS = [
    "gold_id",
    "conversation_id",
    "conversation_context",
    "first_customer_message",
    "latest_customer_message",
    "human_intent",
    "human_escalate",
]


def load_and_validate_golden_set(file_path: Path) -> pd.DataFrame:
    """Load and strictly validate the canonical Golden Set CSV.

    Args:
        file_path: Absolute or relative Path to apple_goldset.csv.

    Returns:
        Validated pandas DataFrame containing the 200 Golden Set examples.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If validation checks fail.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Golden Set file not found at: {path}")

    df = pd.read_csv(path)

    # 1. Exact row count check
    if len(df) != 200:
        raise ValueError(f"Golden Set must contain exactly 200 rows, but found {len(df)}.")

    # 2. Required columns check
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Golden Set is missing required columns: {missing_cols}")

    # 3. Unique gold_id check
    if df["gold_id"].nunique() != 200:
        raise ValueError("Duplicate 'gold_id' values detected in Golden Set.")

    # 4. Unique conversation_id check
    if df["conversation_id"].nunique() != 200:
        raise ValueError("Duplicate 'conversation_id' values detected in Golden Set.")

    # 5. Authoritative intent validation
    invalid_intents = set(df["human_intent"].dropna()) - set(AUTHORITATIVE_INTENTS)
    if invalid_intents:
        raise ValueError(f"Golden Set contains invalid intent values: {invalid_intents}")

    # 6. Valid escalation values check
    invalid_escalate = set(df["human_escalate"].dropna()) - {"YES", "NO"}
    if invalid_escalate:
        raise ValueError(f"Golden Set contains invalid human_escalate values: {invalid_escalate}")

    # 7. No nulls in key ground-truth fields
    for col in ["conversation_id", "human_intent", "human_escalate"]:
        if df[col].isna().any():
            raise ValueError(f"Golden Set contains null values in required column: '{col}'.")

    return df


def reconstruct_conversation(row: pd.Series) -> List[MessageItem]:
    """Reconstruct a multi-turn conversation from a Golden Set row.

    Parses the conversation_context field, preserving dialogue turns and roles.
    Falls back to customer message fields if context parsing yields no customer turns.

    Args:
        row: A pandas Series corresponding to a Golden Set row.

    Returns:
        List of MessageItem Pydantic models.
    """
    raw_context = str(row.get("conversation_context", ""))
    lines = raw_context.splitlines()

    turns = []
    current_role = None
    current_text = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        if line_clean.startswith("Customer:"):
            if current_role and current_text:
                text_block = "\n".join(current_text).strip()
                if text_block:
                    turns.append(MessageItem(role=current_role, text=text_block))
            current_role = MessageRole.CUSTOMER
            current_text = [line_clean[len("Customer:"):].strip()]
        elif line_clean.startswith("AppleSupport:") or line_clean.startswith("Assistant:"):
            if current_role and current_text:
                text_block = "\n".join(current_text).strip()
                if text_block:
                    turns.append(MessageItem(role=current_role, text=text_block))
            current_role = MessageRole.ASSISTANT
            prefix_len = len("AppleSupport:") if line_clean.startswith("AppleSupport:") else len("Assistant:")
            current_text = [line_clean[prefix_len:].strip()]
        else:
            if current_text is not None:
                current_text.append(line_clean)

    if current_role and current_text:
        text_block = "\n".join(current_text).strip()
        if text_block:
            turns.append(MessageItem(role=current_role, text=text_block))

    # Ensure at least one customer turn exists
    has_customer = any(turn.role == MessageRole.CUSTOMER and turn.text.strip() for turn in turns)
    if not has_customer:
        # Fallback to latest_customer_message or first_customer_message
        fallback_msg = str(row.get("latest_customer_message") or row.get("first_customer_message") or "").strip()
        if not fallback_msg:
            fallback_msg = "Need help with my Apple device."
        turns.append(MessageItem(role=MessageRole.CUSTOMER, text=fallback_msg))

    return turns
