from __future__ import annotations

import pytest

from chat_history.repository import (
    ConversationNotFoundError,
    InMemoryConversationRepository,
    InvalidFeedbackTargetError,
)


def test_conversation_lifecycle_is_scoped_to_owner() -> None:
    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("user-a", "PRESTO question")

    user_message = repository.add_message(
        "user-a", conversation.conversation_id, "user", "How do I reload?"
    )
    assistant_message = repository.add_message(
        "user-a",
        conversation.conversation_id,
        "assistant",
        "You can reload online or at a machine.",
        metadata={"contextUsed": True},
    )
    feedback = repository.set_feedback(
        "user-a",
        conversation.conversation_id,
        assistant_message.message_id,
        True,
        "Clear answer",
    )

    reopened = repository.get_conversation("user-a", conversation.conversation_id)
    assert [message.message_id for message in reopened.messages] == [
        user_message.message_id,
        assistant_message.message_id,
    ]
    assert reopened.messages[1].feedback == feedback
    assert repository.list_conversations("user-a")[0].conversation_id == (
        conversation.conversation_id
    )

    with pytest.raises(ConversationNotFoundError):
        repository.get_conversation("user-b", conversation.conversation_id)

    repository.delete_conversation("user-a", conversation.conversation_id)
    assert repository.list_conversations("user-a") == []


def test_feedback_rejects_user_message() -> None:
    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("user-a", "Question")
    message = repository.add_message(
        "user-a", conversation.conversation_id, "user", "Hello"
    )

    with pytest.raises(InvalidFeedbackTargetError):
        repository.set_feedback(
            "user-a", conversation.conversation_id, message.message_id, True
        )