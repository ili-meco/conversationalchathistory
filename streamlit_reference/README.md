# Streamlit Chat History Reference

This folder is a self-contained reference for adding durable, per-user chat
history to a Streamlit application. It does not use Flask and does not modify the
existing Flask reference.

## How it works

1. `identity.py` resolves the trusted user from App Service Easy Auth headers or
   Streamlit OIDC claims.
2. `streamlit_app.py` stores only the selected `conversationId` in
   `st.session_state`.
3. `service.py` saves the new user message and reloads the authoritative
   transcript from Cosmos before calling the AI response function.
4. `cosmos_repository.py` saves the assistant response before the Streamlit page
   reruns.
5. The sidebar queries Cosmos to list and reopen conversations after a refresh or
   a new browser session.

The Cosmos database must contain a `conversations` container with partition key
`/userId`.

## Files

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | Streamlit page, session state, chat UI, reopen, feedback, and delete actions |
| `service.py` | Save, reload trusted transcript, generate response, and save answer flow |
| `identity.py` | Streamlit OIDC, Easy Auth, local identity, and managed-identity credentials |
| `models.py` | Conversation, message, and feedback records with server-generated IDs |
| `repository.py` | Storage contract independent of Streamlit |
| `cosmos_repository.py` | Fabric Cosmos reads and writes using `/userId` |

## Microsoft Foundry response generation

`foundry_response.py` sends the transcript reloaded from Cosmos to the model
deployment identified by `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`.
Locally it uses the Azure CLI credential. On App Service it uses the managed
identity through `DefaultAzureCredential`.

Set `FOUNDRY_AGENT_INSTRUCTIONS` to override the default general-purpose system
instructions without changing the Python source.

Do not rebuild history from browser fields or accept `userId` from a widget.

## Identity options

For Streamlit-managed Microsoft Entra OIDC, configure `.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "<random-secret>"
client_id = "<entra-app-client-id>"
client_secret = "<entra-app-client-secret>"
server_metadata_url = "https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration"
```

Add a login gate near the start of `main()` if Streamlit owns authentication:

```python
if not st.user.is_logged_in:
    st.button("Sign in", on_click=st.login)
    st.stop()
```

When Azure App Service Authentication owns authentication, `identity.py` reads
`X-MS-CLIENT-PRINCIPAL-ID` from `st.context.headers`. Require authentication at
the App Service level so anonymous requests never reach the app.

## Run locally

```powershell
cd conversationalchathistory/streamlit_reference
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
az login --tenant <fabric-tenant-id>
$env:FABRIC_COSMOS_ENDPOINT = "https://<fabric-cosmos-endpoint>"
$env:FABRIC_COSMOS_DATABASE = "GovernanceChatAnalytics"
$env:FABRIC_COSMOS_CONTAINER = "conversations"
$env:FABRIC_TENANT_ID = "<fabric-tenant-id>"
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<foundry-resource>.services.ai.azure.com/api/projects/<project-name>"
$env:FOUNDRY_MODEL = "<model-deployment-name>"
$env:AZURE_TENANT_ID = "<azure-tenant-id>"
$env:CHAT_HISTORY_ALLOW_DEMO_USER = "true"
streamlit run streamlit_app.py
```

Open `http://localhost:8501`. The demo-user fallback is for local development
only and must remain disabled in production.