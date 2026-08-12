"""Resolve the user identity and create credentials for Fabric Cosmos."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ClientAssertionCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)


TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"


class MissingUserIdentityError(PermissionError):
    """Raised when the hosting platform did not authenticate the request."""


class CrossTenantFabricCredential(TokenCredential):
    """Exchange a managed-identity token for a token in the Fabric tenant."""

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
        """Acquire the workload assertion exchanged in the Fabric tenant."""
        return self._managed_identity.get_token(TOKEN_EXCHANGE_SCOPE).token

    def get_token(self, *scopes: str, **kwargs: Any):
        """Delegate resource token requests to the cross-tenant credential."""
        return self._credential.get_token(*scopes, **kwargs)

    def close(self) -> None:
        """Close both credentials and their underlying transports."""
        self._credential.close()
        self._managed_identity.close()


def resolve_user_id(
    headers: Mapping[str, str], user_claims: Mapping[str, Any] | None = None
) -> str:
    """Resolve a platform-authenticated user; never accept a browser form value."""
    # Easy Auth is authoritative when App Service performs authentication.
    principal_id = headers.get("X-MS-CLIENT-PRINCIPAL-ID", "").strip()
    if principal_id:
        return principal_id

    claims = user_claims or {}
    # ``oid`` is stable for an Entra object; ``sub`` supports other OIDC providers.
    oid = str(claims.get("oid") or "").strip()
    if oid:
        return oid

    subject = str(claims.get("sub") or "").strip()
    if subject:
        return subject

    # The fallback is explicit so a production deployment cannot silently share
    # one partition when authentication is misconfigured.
    if os.getenv("CHAT_HISTORY_ALLOW_DEMO_USER", "false").lower() == "true":
        demo_user_id = os.getenv("CHAT_HISTORY_DEMO_USER_ID", "demo-user").strip()
        if demo_user_id:
            return demo_user_id

    raise MissingUserIdentityError(
        "No trusted user identity was provided by Streamlit OIDC or App Service "
        "Authentication."
    )


def create_service_credential() -> TokenCredential:
    """Create a local, managed-identity, or cross-tenant Fabric credential."""
    tenant_id = os.getenv("FABRIC_TENANT_ID")
    client_id = os.getenv("FABRIC_CLIENT_ID")
    managed_identity_client_id = os.getenv("FABRIC_MANAGED_IDENTITY_CLIENT_ID")
    cross_tenant_values = (tenant_id, client_id, managed_identity_client_id)

    # Production cross-tenant access exchanges a managed-identity assertion.
    if all(cross_tenant_values):
        return CrossTenantFabricCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            managed_identity_client_id=managed_identity_client_id,
        )
    if any(cross_tenant_values):
        # A tenant by itself selects Azure CLI authentication for local work.
        if tenant_id and not client_id and not managed_identity_client_id:
            return AzureCliCredential(tenant_id=tenant_id, process_timeout=60)
        raise RuntimeError(
            "Cross-tenant Fabric authentication requires FABRIC_TENANT_ID, "
            "FABRIC_CLIENT_ID, and FABRIC_MANAGED_IDENTITY_CLIENT_ID."
        )

    # Same-tenant App Service deployments resolve their managed identity here.
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)