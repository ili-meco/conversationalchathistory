"""Storage-neutral repository contract and local in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    ConversationRecord,
    FeedbackRecord,
    MessageRecord,
    MessageRole,
    utc_now,
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


class InMemoryConversationRepository(ConversationRepository):
    def __init__(self) -> None:
        self._conversations: dict[tuple[str, str], ConversationRecord] = {}

    def create_conversation(self, user_id: str, title: str) -> ConversationRecord:
        conversation = ConversationRecord(user_id=user_id, title=title)
        self._conversations[(user_id, conversation.conversation_id)] = conversation
        return conversation.model_copy(deep=True)

    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        conversations = [
            conversation.model_copy(deep=True)
            for (owner_id, _), conversation in self._conversations.items()
            if owner_id == user_id
        ]
        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    def get_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        return self._owned_conversation(user_id, conversation_id).model_copy(deep=True)

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord:
        conversation = self._owned_conversation(user_id, conversation_id)
        message = MessageRecord(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        conversation.messages.append(message)
        conversation.updated_at = message.created_at
        return message.model_copy(deep=True)

    def set_feedback(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        helpful: bool,
        comment: str | None = None,
    ) -> FeedbackRecord:
        conversation = self._owned_conversation(user_id, conversation_id)
        message = next(
            (item for item in conversation.messages if item.message_id == message_id),
            None,
        )
        if message is None or message.role != "assistant":
            raise InvalidFeedbackTargetError(
                "Feedback can only target an assistant message in the conversation."
            )

        now = utc_now()
        feedback = FeedbackRecord(
            feedback_id=f"feedback-{message_id}",
            conversation_id=conversation_id,
            message_id=message_id,
            helpful=helpful,
            comment=comment,
            created_at=message.feedback.created_at if message.feedback else now,
            updated_at=now,
        )
        message.feedback = feedback
        conversation.updated_at = now
        return feedback.model_copy(deep=True)

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        self._owned_conversation(user_id, conversation_id)
        del self._conversations[(user_id, conversation_id)]

    def _owned_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        conversation = self._conversations.get((user_id, conversation_id))
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation