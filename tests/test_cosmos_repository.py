from __future__ import annotations

from typing import Any

from azure.core.exceptions import ResourceNotFoundError

from chat_history.cosmos_repository import CosmosConversationRepository


class FakeContainer:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.query_partitions: list[str] = []

    def create_item(self, item: dict[str, Any]) -> None:
        self.items[(item["userId"], item["id"])] = item.copy()

    def upsert_item(self, item: dict[str, Any]) -> None:
        self.create_item(item)

    def read_item(self, item: str, partition_key: str) -> dict[str, Any]:
        try:
            return self.items[(partition_key, item)].copy()
        except KeyError as exc:
            raise ResourceNotFoundError(message="Not found") from exc

    def patch_item(
        self,
        item: str,
        partition_key: str,
        patch_operations: list[dict[str, Any]],
    ) -> None:
        record = self.items[(partition_key, item)]
        record[patch_operations[0]["path"].lstrip("/")] = patch_operations[0][
            "value"
        ]

    def query_items(
        self,
        query: str,
        partition_key: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        self.query_partitions.append(partition_key)
        partition_items = [
            item.copy()
            for (owner_id, _), item in self.items.items()
            if owner_id == partition_key
        ]
        if "type = 'conversation'" in query:
            return [item for item in partition_items if item["type"] == "conversation"]
        conversation_id = next(
            parameter["value"]
            for parameter in parameters or []
            if parameter["name"] == "@conversationId"
        )
        related = [
            item
            for item in partition_items
            if item.get("conversationId") == conversation_id
            and item["type"] != "conversation"
        ]
        if "SELECT VALUE c.id" in query:
            return [item["id"] for item in related]
        return related

    def delete_item(self, item: str, partition_key: str) -> None:
        del self.items[(partition_key, item)]


def test_cosmos_repository_reconstructs_multi_item_conversation() -> None:
    container = FakeContainer()
    repository = CosmosConversationRepository(container)
    conversation = repository.create_conversation("user-a", "PRESTO")
    repository.add_message(
        "user-a", conversation.conversation_id, "user", "How do I reload?"
    )
    assistant = repository.add_message(
        "user-a",
        conversation.conversation_id,
        "assistant",
        "Reload online.",
        metadata={"contextUsed": True},
    )
    repository.set_feedback(
        "user-a", conversation.conversation_id, assistant.message_id, True
    )

    reopened = repository.get_conversation("user-a", conversation.conversation_id)

    assert [message.role for message in reopened.messages] == ["user", "assistant"]
    assert reopened.messages[1].feedback is not None
    assert reopened.messages[1].metadata == {"contextUsed": True}
    assert set(container.query_partitions) == {"user-a"}


def test_cosmos_delete_removes_only_selected_conversation() -> None:
    container = FakeContainer()
    repository = CosmosConversationRepository(container)
    first = repository.create_conversation("user-a", "First")
    second = repository.create_conversation("user-a", "Second")
    repository.add_message("user-a", first.conversation_id, "user", "Delete me")

    repository.delete_conversation("user-a", first.conversation_id)

    assert repository.get_conversation("user-a", second.conversation_id) == second
    assert all(
        item.get("conversationId") != first.conversation_id
        for item in container.items.values()
    )