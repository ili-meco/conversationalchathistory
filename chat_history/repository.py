"""Storage-neutral repository contract and local in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    ConversationRecord,
    FeedbackRecord,
    MessageRecord,
    MessageRole,
)


class ConversationNotFoundError(LookupError):
    pass


class InvalidFeedbackTargetError(ValueError):
    pass


class ConversationRepository(ABC):
    @abstractmethod
    def create_conversation(self, user_id: str, title: str) -> ConversationRecord:
        raise NotImplementedError

    @abstractmethod
    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
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
        raise NotImplementedError

    @abstractmethod
    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        raise NotImplementedError
