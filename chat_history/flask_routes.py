"""Flask blueprint for durable conversation history APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ValidationError

from .identity import MissingUserIdentityError, user_id_from_request
from .models import ConversationRecord
from .repository import (
    ConversationNotFoundError,
    ConversationRepository,
    InvalidFeedbackTargetError,
)


class CreateConversationRequest(BaseModel):
    title: str = "New conversation"


class AddMessageRequest(BaseModel):
    content: str


class FeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = None


@dataclass(frozen=True)
class GeneratedResponse:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


ResponseGenerator = Callable[[str, list[dict[str, str]]], GeneratedResponse]


def _json_model(model: BaseModel, status: int = 200):
    return jsonify(model.model_dump(mode="json", by_alias=True)), status


def _transcript(conversation: ConversationRecord) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in conversation.messages
    ]


def create_chat_history_blueprint(
    repository: ConversationRepository,
    generate_response: ResponseGenerator,
) -> Blueprint:
    blueprint = Blueprint("chat_history", __name__, url_prefix="/api")

    @blueprint.errorhandler(MissingUserIdentityError)
    def missing_identity(error: MissingUserIdentityError):
        return jsonify({"error": str(error)}), 401

    @blueprint.errorhandler(ConversationNotFoundError)
    def conversation_not_found(_error: ConversationNotFoundError):
        return jsonify({"error": "Conversation not found."}), 404

    @blueprint.errorhandler(InvalidFeedbackTargetError)
    def invalid_feedback(error: InvalidFeedbackTargetError):
        return jsonify({"error": str(error)}), 400

    @blueprint.errorhandler(ValidationError)
    def invalid_request(error: ValidationError):
        return jsonify({"error": "Invalid request.", "details": error.errors()}), 400

    @blueprint.post("/conversations")
    def create_conversation():
        payload = CreateConversationRequest.model_validate(request.get_json() or {})
        title = payload.title.strip() or "New conversation"
        conversation = repository.create_conversation(
            user_id_from_request(request), title
        )
        return _json_model(conversation, 201)

    @blueprint.get("/conversations")
    def list_conversations():
        conversations = repository.list_conversations(user_id_from_request(request))
        return jsonify(
            [
                conversation.model_dump(mode="json", by_alias=True)
                for conversation in conversations
            ]
        )

    @blueprint.get("/conversations/<conversation_id>")
    def get_conversation(conversation_id: str):
        conversation = repository.get_conversation(
            user_id_from_request(request), conversation_id
        )
        return _json_model(conversation)

    @blueprint.post("/conversations/<conversation_id>/messages")
    def add_message(conversation_id: str):
        payload = AddMessageRequest.model_validate(request.get_json() or {})
        content = payload.content.strip()
        if not content:
            return jsonify({"error": "Message content is required."}), 400

        user_id = user_id_from_request(request)
        user_message = repository.add_message(
            user_id, conversation_id, "user", content
        )
        conversation = repository.get_conversation(user_id, conversation_id)
        generated = generate_response(content, _transcript(conversation))
        assistant_message = repository.add_message(
            user_id,
            conversation_id,
            "assistant",
            generated.content,
            generated.metadata,
        )
        return (
            jsonify(
                {
                    "userMessage": user_message.model_dump(
                        mode="json", by_alias=True
                    ),
                    "assistantMessage": assistant_message.model_dump(
                        mode="json", by_alias=True
                    ),
                }
            ),
            201,
        )

    @blueprint.put(
        "/conversations/<conversation_id>/messages/<message_id>/feedback"
    )
    def set_feedback(conversation_id: str, message_id: str):
        payload = FeedbackRequest.model_validate(request.get_json() or {})
        feedback = repository.set_feedback(
            user_id_from_request(request),
            conversation_id,
            message_id,
            payload.helpful,
            payload.comment,
        )
        return _json_model(feedback)

    @blueprint.delete("/conversations/<conversation_id>")
    def delete_conversation(conversation_id: str):
        repository.delete_conversation(
            user_id_from_request(request), conversation_id
        )
        return Response(status=204)

    return blueprint