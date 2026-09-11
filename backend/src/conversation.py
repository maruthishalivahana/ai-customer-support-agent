"""Conversation state representation and multi-turn context tracking.

Provides clean abstractions over customer-assistant dialogue turns, enabling
context-aware decision-making beyond isolated single-message queries.
"""

from typing import List, Optional

from src.schemas import MessageItem, MessageRole


class ConversationState:
    """Manages multi-turn conversation history and dialogue context extraction."""

    def __init__(
        self,
        conversation_id: Optional[str] = None,
        messages: Optional[List[MessageItem]] = None,
    ) -> None:
        self.conversation_id = conversation_id or "conv_default"
        self.messages: List[MessageItem] = messages or []

    @property
    def turns_count(self) -> int:
        """Total number of turns across all roles."""
        return len(self.messages)

    @property
    def customer_messages(self) -> List[MessageItem]:
        """All turns authored by the customer in chronological order."""
        return [m for m in self.messages if m.role == MessageRole.CUSTOMER]

    @property
    def assistant_messages(self) -> List[MessageItem]:
        """All turns authored by the assistant in chronological order."""
        return [m for m in self.messages if m.role == MessageRole.ASSISTANT]

    @property
    def latest_customer_message(self) -> MessageItem:
        """The most recent message from the customer."""
        cust_msgs = self.customer_messages
        if not cust_msgs:
            raise ValueError("Conversation contains no customer messages.")
        return cust_msgs[-1]

    @property
    def latest_message(self) -> MessageItem:
        """The very last message in the sequence."""
        if not self.messages:
            raise ValueError("Conversation contains no messages.")
        return self.messages[-1]

    def get_full_customer_text(self) -> str:
        """Concatenate all customer messages across turns into a single unified string."""
        return " ".join(m.text.strip() for m in self.customer_messages)

    def get_effective_query(self) -> str:
        """Derive the effective query for classification and retrieval.

        If previous customer messages exist, incorporates pertinent prior context
        so that subsequent clarifying turns (e.g. 'My Wi-Fi won't connect' following
        'It stopped working after update') retain the full scope of the problem.
        """
        cust_msgs = self.customer_messages
        if not cust_msgs:
            return ""

        if len(cust_msgs) == 1:
            return cust_msgs[0].text.strip()

        # Multi-turn: combine preceding customer context with the latest clarification
        latest_text = cust_msgs[-1].text.strip()
        preceding_text = " ".join(m.text.strip() for m in cust_msgs[:-1])

        # Avoid simple duplicate phrases
        if latest_text.lower() in preceding_text.lower():
            return preceding_text

        return f"{preceding_text} {latest_text}".strip()

    def get_formatted_history(self, max_turns: int = 6) -> str:
        """Format the recent dialogue turns into a human-readable transcript."""
        recent_turns = self.messages[-max_turns:]
        lines = []
        for turn in recent_turns:
            role_label = "Customer" if turn.role == MessageRole.CUSTOMER else "Assistant"
            lines.append(f"{role_label}: {turn.text.strip()}")
        return "\n".join(lines)

    def add_customer_message(self, text: str) -> None:
        """Append a customer turn."""
        self.messages.append(MessageItem(role=MessageRole.CUSTOMER, text=text))

    def add_assistant_message(self, text: str) -> None:
        """Append an assistant turn."""
        self.messages.append(MessageItem(role=MessageRole.ASSISTANT, text=text))
