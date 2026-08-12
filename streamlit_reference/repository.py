"""Storage contract used by the Streamlit controller."""

from __future__ import annotations

from abc import ABC, abstractmethod

from models import ConversationRecord, FeedbackRecord, MessageRecord, MessageRole


class ConversationNotFoundError(LookupError):
    """Raised when a conversation is missing from the current user partition."""


class InvalidFeedbackTargetError(ValueError):
    """Raised when feedback does not target an assistant message."""


class ConversationRepository(ABC):
    """Storage boundary that keeps Streamlit independent from Cosmos details."""

    @abstractmethod
    def create_conversation(self, user_id: str, title: str) -> ConversationRecord:
        """Create a server-identified conversation owned by ``user_id``."""
        raise NotImplementedError

    @abstractmethod
    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        """List conversation headers from only the user's partition."""
        raise NotImplementedError

    @abstractmethod
    def get_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        """Load and hydrate one conversation after checking ownership."""
        raise NotImplementedError

    @abstractmethod
    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord:
        """Append a server-identified message to an owned conversation."""
        raise NotImplementedError

    @abstractmethod
    def set_feedback(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        helpful: bool,
        comment: str | None = None,
    ) -> FeedbackRecord:
        """Create or replace feedback for one assistant message."""
        raise NotImplementedError

    @abstractmethod
    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        """Delete an owned conversation and its dependent records."""
        raise NotImplementedError