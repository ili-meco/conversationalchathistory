# Conversational Chat History

Production runtime code for adding durable, per-user chat history to an existing
Flask web application hosted on Azure App Service. Conversations, messages, and
feedback are stored in Cosmos DB in Microsoft Fabric.

## Files

| File | Purpose |
| --- | --- |
| `chat_history/models.py` | Defines conversation, message, and feedback records |
| `chat_history/repository.py` | Defines the storage operations required by the API |
| `chat_history/cosmos_repository.py` | Creates, reads, updates, and deletes Fabric Cosmos records |
| `chat_history/identity.py` | Resolves the signed-in user and creates Azure/Fabric credentials |
| `chat_history/flask_routes.py` | Adds conversation, message, feedback, and delete routes to Flask |
| `chat_history/__init__.py` | Exposes the runtime package interface |
| `requirements.txt` | Lists required Python dependencies |
| `.env.example` | Lists required App Service configuration |
| `pyproject.toml` | Makes the runtime code installable as a Python package |
| `LICENSE` | MIT license |

## Cosmos configuration

The target database must contain a `conversations` container with partition key:

```text
/userId
```

Configure these App Service settings:

```text
FABRIC_COSMOS_ENDPOINT=<fabric-cosmos-endpoint>
FABRIC_COSMOS_DATABASE=<database-name>
FABRIC_COSMOS_CONTAINER=conversations
```

For cross-tenant Fabric access, also configure:

```text
FABRIC_TENANT_ID=<fabric-tenant-id>
FABRIC_CLIENT_ID=<multi-tenant-app-registration-client-id>
FABRIC_MANAGED_IDENTITY_CLIENT_ID=<user-assigned-managed-identity-client-id>
```

Enable App Service Authentication with Microsoft Entra ID. The API reads
`X-MS-CLIENT-PRINCIPAL-ID` and uses that value as the conversation owner and
Cosmos partition key.

## Flask registration

Create the Cosmos repository once during application startup and register the
chat-history blueprint. The required callback receives the new user message and
the authoritative transcript reloaded from Cosmos, then returns a
`GeneratedResponse` produced by the application's existing Azure OpenAI logic.

The blueprint exposes:

```text
POST   /api/conversations
GET    /api/conversations
GET    /api/conversations/{conversationId}
POST   /api/conversations/{conversationId}/messages
PUT    /api/conversations/{conversationId}/messages/{messageId}/feedback
DELETE /api/conversations/{conversationId}
```

The browser should send only the selected `conversationId` and the new message.
The server owns and reconstructs the conversation history.