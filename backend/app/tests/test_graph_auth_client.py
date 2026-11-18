import asyncio
from unittest.mock import Mock

import httpx
import pytest

from app.integrations.microsoft_graph import auth, client


def test_graph_auth_rejects_missing_credentials(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "GRAPH_TENANT_ID", None)
    monkeypatch.setattr(auth.settings, "GRAPH_CLIENT_ID", None)
    monkeypatch.setattr(auth.settings, "GRAPH_CLIENT_SECRET", None)

    with pytest.raises(ValueError, match="credentials are not configured"):
        auth.GraphAuth.get_access_token()


def test_graph_auth_returns_application_token(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "GRAPH_TENANT_ID", "tenant-id")
    monkeypatch.setattr(auth.settings, "GRAPH_CLIENT_ID", "client-id")
    monkeypatch.setattr(auth.settings, "GRAPH_CLIENT_SECRET", "client-secret")
    acquire_token = Mock(return_value={"access_token": "test-token"})
    application = Mock(acquire_token_for_client=acquire_token)
    confidential_client = Mock(return_value=application)
    monkeypatch.setattr(
        auth.msal,
        "ConfidentialClientApplication",
        confidential_client,
    )

    token = auth.GraphAuth.get_access_token()

    assert token == "test-token"
    confidential_client.assert_called_once_with(
        client_id="client-id",
        client_credential="client-secret",
        authority="https://login.microsoftonline.com/tenant-id",
    )
    acquire_token.assert_called_once_with(
        scopes=["https://graph.microsoft.com/.default"]
    )


def test_graph_client_get_sends_bearer_token_and_returns_json(
    monkeypatch,
) -> None:
    response = Mock()
    response.json.return_value = {"value": [{"id": "user-1"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def get(self, url, headers):
            self.url = url
            self.headers = headers
            return response

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        client.settings,
        "GRAPH_BASE_URL",
        "https://graph.example.test/v1.0",
    )

    result = asyncio.run(
        client.GraphClient("test-token").get("users?$top=1")
    )

    assert result == {"value": [{"id": "user-1"}]}
    assert fake_client.url == (
        "https://graph.example.test/v1.0/users?$top=1"
    )
    assert fake_client.headers == {
        "Authorization": "Bearer test-token"
    }
    response.raise_for_status.assert_called_once_with()


def test_graph_client_propagates_http_errors(monkeypatch) -> None:
    response = Mock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Forbidden",
        request=httpx.Request("GET", "https://graph.example.test/users"),
        response=httpx.Response(403),
    )

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def get(self, url, headers):
            return response

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.GraphClient("test-token").get("users"))
