"""Records stored in the Fabric Cosmos conversations container."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


MessageRole = Literal["user", "assistant"]


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for durable storage."""
    return datetime.now(timezone.utc)


def _to_camel(value: str) -> str:
    """Map Python field names to the camelCase Cosmos document schema."""
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class PersistenceModel(BaseModel):
    """Base model that accepts Python names and serializes Cosmos aliases."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class FeedbackRecord(PersistenceModel):
    """Feedback attached to one assistant message."""

    feedback_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    message_id: str
    helpful: bool
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MessageRecord(PersistenceModel):
    """One user or assistant turn in a conversation."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    feedback: FeedbackRecord | None = None


class ConversationRecord(PersistenceModel):
    """Conversation header plus hydrated messages returned to the application."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    title: str
    status: Literal["active", "completed"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    schema_version: int = 1
    messages: list[MessageRecord] = Field(default_factory=list)