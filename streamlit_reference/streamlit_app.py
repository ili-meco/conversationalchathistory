"""Reference Streamlit UI for durable, per-user Fabric Cosmos chat history."""

from __future__ import annotations

from typing import Any

import streamlit as st

from cosmos_repository import create_cosmos_repository
from foundry_response import generate_foundry_response
from identity import MissingUserIdentityError, resolve_user_id
from repository import ConversationNotFoundError, ConversationRepository
from service import ChatHistoryService, GeneratedResponse


SELECTED_CONVERSATION_KEY = "selected_conversation_id"


@st.cache_resource(show_spinner="Connecting to Fabric Cosmos...")
def get_repository() -> ConversationRepository:
    """Reuse one thread-safe Cosmos client across Streamlit reruns."""
    return create_cosmos_repository()


def generate_response(
    new_message: str, trusted_transcript: list[dict[str, str]]
) -> GeneratedResponse:
    """Delegate response generation to the configured Foundry deployment."""
    return generate_foundry_response(new_message, trusted_transcript)


def current_user_id() -> str:
    """Resolve identity from OIDC claims or App Service Easy Auth headers."""
    claims: dict[str, Any] = {}
    if getattr(st.user, "is_logged_in", False):
        claims = st.user.to_dict()
    return resolve_user_id(st.context.headers, claims)


def select_conversation(conversation_id: str) -> None:
    """Keep only the selected ID in session state; Cosmos stores the history."""
    st.session_state[SELECTED_CONVERSATION_KEY] = conversation_id


def clear_selection() -> None:
    """Clear browser-local selection after deletion or an ownership miss."""
    st.session_state.pop(SELECTED_CONVERSATION_KEY, None)


def render_sidebar(service: ChatHistoryService, user_id: str) -> None:
    """Render durable conversations loaded from the current user partition."""
    with st.sidebar:
        st.header("Conversations")
        if st.button("New conversation", type="primary", use_container_width=True):
            conversation = service.create_conversation(user_id)
            select_conversation(conversation.conversation_id)
            st.rerun()

        for conversation in service.list_conversations(user_id):
            selected = (
                conversation.conversation_id
                == st.session_state.get(SELECTED_CONVERSATION_KEY)
            )
            label = f"{'Selected: ' if selected else ''}{conversation.title}"
            if st.button(
                label,
                key=f"open-{conversation.conversation_id}",
                use_container_width=True,
            ):
                select_conversation(conversation.conversation_id)
                st.rerun()


def render_messages(
    service: ChatHistoryService, user_id: str, conversation_id: str
) -> None:
    """Render persisted turns and actions for the selected conversation."""
    conversation = service.open_conversation(user_id, conversation_id)
    title_column, delete_column = st.columns([5, 1])
    title_column.subheader(conversation.title)
    if delete_column.button(
        "Delete", key=f"delete-{conversation_id}", use_container_width=True
    ):
        service.delete_conversation(user_id, conversation_id)
        clear_selection()
        st.rerun()

    for message in conversation.messages:
        with st.chat_message(message.role):
            st.markdown(message.content)
            if message.role == "assistant":
                helpful_column, not_helpful_column = st.columns(2)
                if helpful_column.button(
                    "Helpful",
                    key=f"helpful-{message.message_id}",
                    use_container_width=True,
                ):
                    service.set_feedback(
                        user_id, conversation_id, message.message_id, True
                    )
                    st.rerun()
                if not_helpful_column.button(
                    "Not helpful",
                    key=f"not-helpful-{message.message_id}",
                    use_container_width=True,
                ):
                    service.set_feedback(
                        user_id, conversation_id, message.message_id, False
                    )
                    st.rerun()


def main() -> None:
    """Render the Streamlit page and coordinate each rerun."""
    st.set_page_config(page_title="Durable chat history", page_icon=":material/chat:")
    st.title("Durable chat history")

    try:
        user_id = current_user_id()
        service = ChatHistoryService(get_repository(), generate_response)
        render_sidebar(service, user_id)

        # Session state remembers navigation only. Every message is reloaded from
        # Cosmos by the service before it is displayed or sent to Foundry.
        conversation_id = st.session_state.get(SELECTED_CONVERSATION_KEY)
        if not conversation_id:
            st.info("Create a conversation or reopen one from the sidebar.")
            return

        render_messages(service, user_id, conversation_id)
        if prompt := st.chat_input("Send a message"):
            with st.spinner("Generating response..."):
                service.send_message(user_id, conversation_id, prompt)
            st.rerun()
    except MissingUserIdentityError as exc:
        st.error(str(exc))
        st.info(
            "Configure Streamlit OIDC, enable App Service Authentication, or use "
            "the local-only demo identity described in README.md."
        )
    except ConversationNotFoundError:
        clear_selection()
        st.warning("The selected conversation no longer exists.")
        st.rerun()


if __name__ == "__main__":
    main()