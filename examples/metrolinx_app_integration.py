"""Registration pattern for the existing Metrolinx Flask application."""

from __future__ import annotations

from typing import Any, Callable

from flask import Flask

from chat_history.cosmos_repository import create_cosmos_repository
from chat_history.flask_routes import (
    GeneratedResponse,
    create_chat_history_blueprint,
)


def register_chat_history(
    app: Flask,
    openai_client: Any,
    deployment_name: str,
    system_prompt: str,
    search_knowledge_base: Callable[[str], str],
) -> None:
    """Register durable routes using the app's existing Search and OpenAI clients."""
    repository = create_cosmos_repository()

    def generate_response(
        user_message: str,
        transcript: list[dict[str, str]],
    ) -> GeneratedResponse:
        context = search_knowledge_base(user_message)
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Relevant information from the knowledge base:\n\n" + context
                    ),
                }
            )
        messages.extend(transcript)

        response = openai_client.chat.completions.create(
            model=deployment_name,
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )
        return GeneratedResponse(
            content=response.choices[0].message.content,
            metadata={
                "contextUsed": bool(context),
                "model": deployment_name,
                "openAIResponseId": getattr(response, "id", None),
            },
        )

    app.register_blueprint(
        create_chat_history_blueprint(repository, generate_response)
    )