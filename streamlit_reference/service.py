"""Framework-neutral orchestration used by the Streamlit page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from models import ConversationRecord, FeedbackRecord, MessageRecord
from repository import ConversationRepository


@dataclass(frozen=True)
class GeneratedResponse:
    """AI response and telemetry that will be persisted together."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


ResponseGenerator = Callable[[str, list[dict[str, str]]], GeneratedResponse]


@dataclass(frozen=True)
class SavedTurn:
    """The user and assistant records created by one request."""

    user_message: MessageRecord
    assistant_message: MessageRecord


class ChatHistoryService:
    """Coordinate durable history without depending on a UI framework."""

    def __init__(
        self,
        repository: ConversationRepository,
        generate_response: ResponseGenerator,
    ) -> None:
        self._repository = repository
        self._generate_response = generate_response

    def create_conversation(
        self, user_id: str, title: str = "New conversation"
    ) -> ConversationRecord:
        """Create a conversation with a non-empty display title."""
        return self._repository.create_conversation(
            user_id, title.strip() or "New conversation"
        )

    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        """Return the user's persisted conversations for the sidebar."""
        return self._repository.list_conversations(user_id)

    def open_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        """Reopen one persisted conversation using its server-generated ID."""
        return self._repository.get_conversation(user_id, conversation_id)

    def send_message(
        self, user_id: str, conversation_id: str, content: str
    ) -> SavedTurn:
        """Persist the user turn, generate from trusted history, and save the answer."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content is required.")

        user_message = self._repository.add_message(
            user_id, conversation_id, "user", clean_content
        )
        # Reload after the write so model context comes from authoritative storage,
        # not from browser state that a caller could omit or alter.
        conversation = self._repository.get_conversation(user_id, conversation_id)
        transcript = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
        ]
        generated = self._generate_response(clean_content, transcript)
        assistant_message = self._repository.add_message(
            user_id,
            conversation_id,
            "assistant",
            generated.content,
            generated.metadata,
        )
        return SavedTurn(user_message, assistant_message)

    def set_feedback(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        helpful: bool,
        comment: str | None = None,
    ) -> FeedbackRecord:
        """Persist feedback after repository-level target validation."""
        return self._repository.set_feedback(
            user_id, conversation_id, message_id, helpful, comment
        )

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        """Delete a conversation through the repository ownership boundary."""
        self._repository.delete_conversation(user_id, conversation_id)