"""Create the chat-history container in an existing Fabric Cosmos database."""

from __future__ import annotations

import argparse
import os

from azure.cosmos import CosmosClient, PartitionKey

from chat_history.identity import create_service_credential


def required(value: str | None, environment_name: str) -> str:
    resolved = value or os.getenv(environment_name)
    if not resolved:
        raise SystemExit(
            f"Provide --{environment_name.lower().replace('_', '-')} or set "
            f"{environment_name}."
        )
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint")
    parser.add_argument("--database")
    parser.add_argument("--container", default="conversations")
    arguments = parser.parse_args()

    endpoint = required(arguments.endpoint, "FABRIC_COSMOS_ENDPOINT")
    database_name = required(arguments.database, "FABRIC_COSMOS_DATABASE")
    credential = create_service_credential()
    client = CosmosClient(endpoint, credential=credential)
    try:
        database = client.get_database_client(database_name)
        database.read()
        container = database.create_container_if_not_exists(
            id=arguments.container,
            partition_key=PartitionKey(path="/userId"),
        )
        properties = container.read()
        print(
            f"Container '{properties['id']}' is ready in database "
            f"'{database_name}' with partition key /userId."
        )
    finally:
        client.close()
        close = getattr(credential, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()