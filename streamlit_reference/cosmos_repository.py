"""Synchronous Fabric Cosmos storage for the Streamlit application."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.cosmos import CosmosClient

from identity import create_service_credential
from models import (
    ConversationRecord,
    FeedbackRecord,
    MessageRecord,
    MessageRole,
    utc_now,
)
from repository import (
    ConversationNotFoundError,
    ConversationRepository,
    InvalidFeedbackTargetError,
)


def _required_env(name: str) -> str:
    """Return a required Cosmos setting or fail before creating the client."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class CosmosConversationRepository(ConversationRepository):
    """Store conversation, message, and feedback items in one user partition."""

    def __init__(self, container: Any, client: CosmosClient | None = None) -> None:
        self._container = container
        self._client = client

    def create_conversation(self, user_id: str, title: str) -> ConversationRecord:
        """Create the header item that establishes user ownership."""
        conversation = ConversationRecord(user_id=user_id, title=title)
        self._container.create_item(self._conversation_item(conversation))
        return conversation

    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        """List headers using a single-partition query ordered by activity."""
        items = self._container.query_items(
            query=(
                "SELECT * FROM c WHERE c.type = 'conversation' "
                "ORDER BY c.updatedAt DESC"
            ),
            partition_key=user_id,
        )
        return [self._conversation_from_item(item) for item in items]

    def get_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        """Hydrate messages and feedback from the owned user partition."""
        conversation = self._read_conversation(user_id, conversation_id)
        records = self._container.query_items(
            query=(
                "SELECT * FROM c WHERE c.conversationId = @conversationId "
                "AND c.type != 'conversation'"
            ),
            parameters=[{"name": "@conversationId", "value": conversation_id}],
            partition_key=user_id,
        )
        messages: dict[str, MessageRecord] = {}
        feedback_by_message: dict[str, FeedbackRecord] = {}
        for item in records:
            if item.get("type") == "message":
                message = self._message_from_item(item)
                messages[message.message_id] = message
            elif item.get("type") == "feedback":
                feedback = self._feedback_from_item(item)
                feedback_by_message[feedback.message_id] = feedback

        for message_id, feedback in feedback_by_message.items():
            if message_id in messages:
                messages[message_id].feedback = feedback
        conversation.messages = sorted(
            messages.values(), key=lambda message: message.created_at
        )
        return conversation

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord:
        """Verify ownership, append a message, and update sidebar ordering."""
        # This point read prevents callers from writing into another user's
        # conversation by guessing or obtaining its conversation ID.
        self._read_conversation(user_id, conversation_id)
        message = MessageRecord(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._container.create_item(self._message_item(user_id, message))
        self._touch_conversation(user_id, conversation_id, message.created_at)
        return message

    def set_feedback(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        helpful: bool,
        comment: str | None = None,
    ) -> FeedbackRecord:
        """Upsert feedback only when the target is an assistant message."""
        self._read_conversation(user_id, conversation_id)
        try:
            message_item = self._container.read_item(
                item=message_id, partition_key=user_id
            )
        except ResourceNotFoundError as exc:
            raise InvalidFeedbackTargetError(
                "Feedback can only target an assistant message in the conversation."
            ) from exc
        if (
            message_item.get("type") != "message"
            or message_item.get("role") != "assistant"
            or message_item.get("conversationId") != conversation_id
        ):
            raise InvalidFeedbackTargetError(
                "Feedback can only target an assistant message in the conversation."
            )

        # A deterministic ID makes feedback idempotent: one record per message.
        feedback_id = f"feedback-{message_id}"
        now = utc_now()
        try:
            existing = self._container.read_item(
                item=feedback_id, partition_key=user_id
            )
            created_at = datetime.fromisoformat(existing["createdAt"])
        except ResourceNotFoundError:
            created_at = now
        feedback = FeedbackRecord(
            feedback_id=feedback_id,
            conversation_id=conversation_id,
            message_id=message_id,
            helpful=helpful,
            comment=comment,
            created_at=created_at,
            updated_at=now,
        )
        self._container.upsert_item(self._feedback_item(user_id, feedback))
        self._touch_conversation(user_id, conversation_id, now)
        return feedback

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        """Delete child records before deleting the conversation header."""
        self._read_conversation(user_id, conversation_id)
        item_ids = self._container.query_items(
            query=(
                "SELECT VALUE c.id FROM c "
                "WHERE c.conversationId = @conversationId "
                "AND c.type != 'conversation'"
            ),
            parameters=[{"name": "@conversationId", "value": conversation_id}],
            partition_key=user_id,
        )
        for item_id in item_ids:
            self._container.delete_item(item=item_id, partition_key=user_id)
        self._container.delete_item(item=conversation_id, partition_key=user_id)

    def _read_conversation(
        self, user_id: str, conversation_id: str
    ) -> ConversationRecord:
        """Point-read a header and enforce its type and owner."""
        try:
            item = self._container.read_item(
                item=conversation_id, partition_key=user_id
            )
        except ResourceNotFoundError as exc:
            raise ConversationNotFoundError(conversation_id) from exc
        if item.get("type") != "conversation" or item.get("userId") != user_id:
            raise ConversationNotFoundError(conversation_id)
        return self._conversation_from_item(item)

    def _touch_conversation(
        self, user_id: str, conversation_id: str, updated_at: datetime
    ) -> None:
        """Patch activity time without replacing the conversation document."""
        self._container.patch_item(
            item=conversation_id,
            partition_key=user_id,
            patch_operations=[
                {
                    "op": "replace",
                    "path": "/updatedAt",
                    "value": updated_at.isoformat(),
                }
            ],
        )

    @staticmethod
    def _conversation_item(conversation: ConversationRecord) -> dict[str, Any]:
        return {
            "id": conversation.conversation_id,
            "type": "conversation",
            "conversationId": conversation.conversation_id,
            "userId": conversation.user_id,
            "title": conversation.title,
            "status": conversation.status,
            "createdAt": conversation.created_at.isoformat(),
            "updatedAt": conversation.updated_at.isoformat(),
            "schemaVersion": conversation.schema_version,
        }

    @staticmethod
    def _message_item(user_id: str, message: MessageRecord) -> dict[str, Any]:
        return {
            "id": message.message_id,
            "type": "message",
            "conversationId": message.conversation_id,
            "userId": user_id,
            "messageId": message.message_id,
            "role": message.role,
            "content": message.content,
            "createdAt": message.created_at.isoformat(),
            "metadata": message.metadata,
        }

    @staticmethod
    def _feedback_item(user_id: str, feedback: FeedbackRecord) -> dict[str, Any]:
        return {
            "id": feedback.feedback_id,
            "type": "feedback",
            "conversationId": feedback.conversation_id,
            "userId": user_id,
            "feedbackId": feedback.feedback_id,
            "messageId": feedback.message_id,
            "helpful": feedback.helpful,
            "comment": feedback.comment,
            "createdAt": feedback.created_at.isoformat(),
            "updatedAt": feedback.updated_at.isoformat(),
        }

    @staticmethod
    def _conversation_from_item(item: dict[str, Any]) -> ConversationRecord:
        return ConversationRecord(
            conversation_id=item["conversationId"],
            user_id=item["userId"],
            title=item["title"],
            status=item.get("status", "active"),
            created_at=item["createdAt"],
            updated_at=item["updatedAt"],
            schema_version=item.get("schemaVersion", 1),
        )

    @staticmethod
    def _message_from_item(item: dict[str, Any]) -> MessageRecord:
        return MessageRecord(
            message_id=item["messageId"],
            conversation_id=item["conversationId"],
            role=item["role"],
            content=item["content"],
            created_at=item["createdAt"],
            metadata=item.get("metadata", {}),
        )

    @staticmethod
    def _feedback_from_item(item: dict[str, Any]) -> FeedbackRecord:
        return FeedbackRecord(
            feedback_id=item["feedbackId"],
            conversation_id=item["conversationId"],
            message_id=item["messageId"],
            helpful=item["helpful"],
            comment=item.get("comment"),
            created_at=item["createdAt"],
            updated_at=item["updatedAt"],
        )


def create_cosmos_repository() -> CosmosConversationRepository:
    """Create one reusable Cosmos client from environment configuration."""
    endpoint = os.getenv("CHAT_HISTORY_COSMOS_ENDPOINT") or _required_env(
        "FABRIC_COSMOS_ENDPOINT"
    )
    database_name = os.getenv("CHAT_HISTORY_COSMOS_DATABASE") or _required_env(
        "FABRIC_COSMOS_DATABASE"
    )
    container_name = os.getenv(
        "CHAT_HISTORY_COSMOS_CONTAINER",
        os.getenv("FABRIC_COSMOS_CONTAINER", "conversations"),
    )
    client = CosmosClient(endpoint, credential=create_service_credential())
    container = client.get_database_client(database_name).get_container_client(
        container_name
    )
    return CosmosConversationRepository(container, client)