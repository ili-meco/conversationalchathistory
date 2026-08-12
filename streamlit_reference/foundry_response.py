"""Generate chat responses with the configured Microsoft Foundry deployment."""

from __future__ import annotations

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential

from service import GeneratedResponse


DEFAULT_AGENT_INSTRUCTIONS = """
You are a helpful enterprise assistant. Continue the conversation using only the
trusted transcript supplied by the application. Give a clear, concise answer to
the latest user message. Do not mention internal persistence or implementation
details unless the user asks about them.
""".strip()


def _required_env(name: str) -> str:
    """Read a required deployment setting without embedding service secrets."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _credential_options() -> dict[str, str | int]:
    """Pin local Azure CLI authentication when tenant or subscription is known."""
    options: dict[str, str | int] = {
        "process_timeout": int(os.getenv("AZURE_CLI_PROCESS_TIMEOUT", "60"))
    }
    if subscription_id := os.getenv("AZURE_SUBSCRIPTION_ID"):
        options["subscription"] = subscription_id
    elif tenant_id := os.getenv("AZURE_TENANT_ID"):
        options["tenant_id"] = tenant_id
    return options


def _create_runtime_credential() -> AsyncTokenCredential:
    """Use managed identity in Azure and the developer's Azure CLI locally."""
    if os.getenv("WEBSITE_INSTANCE_ID") or os.getenv("IDENTITY_ENDPOINT"):
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return AzureCliCredential(**_credential_options())


def _format_transcript(transcript: list[dict[str, str]]) -> str:
    """Convert trusted records into the text format accepted by the agent."""
    return "\n".join(
        f"{message['role'].title()}: {message['content']}" for message in transcript
    )


async def _generate_foundry_response(
    new_message: str, trusted_transcript: list[dict[str, str]]
) -> GeneratedResponse:
    """Invoke the configured Foundry model and return persistence-ready output."""
    project_endpoint = _required_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _required_env("FOUNDRY_MODEL")
    instructions = os.getenv(
        "FOUNDRY_AGENT_INSTRUCTIONS", DEFAULT_AGENT_INSTRUCTIONS
    ).strip()

    async with _create_runtime_credential() as credential:
        client = FoundryChatClient(
            credential=credential,
            project_endpoint=project_endpoint,
            model=model,
        )
        agent = client.as_agent(
            name="StreamlitChatHistoryAgent",
            instructions=instructions,
        )
        # The service loaded this transcript from Cosmos after saving the latest
        # user turn, so no browser-supplied history reaches the model directly.
        response = await agent.run(
            "Continue this trusted conversation and answer the latest user message.\n\n"
            f"<conversation>\n{_format_transcript(trusted_transcript)}\n"
            "</conversation>"
        )

    content = response.text.strip()
    if not content:
        raise RuntimeError("The configured Foundry deployment returned an empty response.")
    return GeneratedResponse(
        content=content,
        metadata={
            "provider": "Microsoft Foundry",
            "model": model,
            "transcriptTurns": len(trusted_transcript),
            "requestMessage": new_message,
        },
    )


def generate_foundry_response(
    new_message: str, trusted_transcript: list[dict[str, str]]
) -> GeneratedResponse:
    """Run the async Foundry client from Streamlit's synchronous callback."""
    return asyncio.run(_generate_foundry_response(new_message, trusted_transcript))