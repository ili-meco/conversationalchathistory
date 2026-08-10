"""App Service user identity and Azure service credential helpers."""

from __future__ import annotations

import os

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ClientAssertionCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)
from flask import Request


TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"


class MissingUserIdentityError(PermissionError):
    pass


class CrossTenantFabricCredential(TokenCredential):
    """Exchange an App Service managed-identity token into a Fabric-tenant token."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        managed_identity_client_id: str,
    ) -> None:
        self._managed_identity = ManagedIdentityCredential(
            client_id=managed_identity_client_id
        )
        self._credential = ClientAssertionCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            func=self._get_assertion,
        )

    def _get_assertion(self) -> str:
        return self._managed_identity.get_token(TOKEN_EXCHANGE_SCOPE).token

    def get_token(self, *scopes: str, **kwargs):
        return self._credential.get_token(*scopes, **kwargs)

    def close(self) -> None:
        self._credential.close()
        self._managed_identity.close()


def user_id_from_request(request: Request) -> str:
    """Return the Easy Auth principal ID, with an explicit local-only fallback."""
    principal_id = request.headers.get("X-MS-CLIENT-PRINCIPAL-ID", "").strip()
    if principal_id:
        return principal_id

    if os.getenv("CHAT_HISTORY_ALLOW_DEMO_USER", "false").lower() == "true":
        demo_user_id = os.getenv("CHAT_HISTORY_DEMO_USER_ID", "demo-user").strip()
        if demo_user_id:
            return demo_user_id

    raise MissingUserIdentityError(
        "App Service Authentication did not provide a user principal ID."
    )


def create_service_credential() -> TokenCredential:
    """Create a local, managed-identity, or cross-tenant Fabric credential."""
    tenant_id = os.getenv("FABRIC_TENANT_ID")
    client_id = os.getenv("FABRIC_CLIENT_ID")
    managed_identity_client_id = os.getenv("FABRIC_MANAGED_IDENTITY_CLIENT_ID")
    cross_tenant_values = (tenant_id, client_id, managed_identity_client_id)

    if all(cross_tenant_values):
        return CrossTenantFabricCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            managed_identity_client_id=managed_identity_client_id,
        )
    if any(cross_tenant_values):
        if tenant_id and not client_id and not managed_identity_client_id:
            return AzureCliCredential(tenant_id=tenant_id, process_timeout=60)
        raise RuntimeError(
            "Cross-tenant Fabric authentication requires FABRIC_TENANT_ID, "
            "FABRIC_CLIENT_ID, and FABRIC_MANAGED_IDENTITY_CLIENT_ID."
        )

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)