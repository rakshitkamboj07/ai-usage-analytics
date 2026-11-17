import csv
import json
import time
from io import StringIO
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)

from app.core.config import settings

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_REQUEST_TIMEOUT_SECONDS = 30
_TOKEN_REFRESH_BUFFER_SECONDS = 60
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_COPILOT_PERIODS = {"D7", "D28", "D90", "D180", "ALL"}
_TEAMS_PERIODS = {"D7", "D30", "D90", "D180", "ALL"}


class GraphConfigurationError(ValueError):
    pass


class GraphResponseError(RuntimeError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class MicrosoftGraphClient:
    def __init__(
        self,
        tenant_id: str | None = settings.GRAPH_TENANT_ID,
        client_id: str | None = settings.GRAPH_CLIENT_ID,
        client_secret: str | None = settings.GRAPH_CLIENT_SECRET,
    ) -> None:
        if not tenant_id or not client_id or not client_secret:
            raise GraphConfigurationError(
                "Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, and "
                "GRAPH_CLIENT_SECRET in the backend environment."
            )
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._graph_opener = build_opener(_NoRedirectHandler)

    def get_copilot_usage_report(
        self,
        period: str = "D90",
    ) -> list[dict[str, str]]:
        if period not in _COPILOT_PERIODS:
            raise ValueError(
                f"Unsupported Copilot report period: {period}"
            )
        endpoint = (
            "/copilot/reports/"
            "getMicrosoft365CopilotUsageUserDetail"
            f"(period='{period}',version='v2')"
        )
        return self._get_report_csv(endpoint)

    def get_teams_user_activity_report(
        self,
        period: str = "D90",
    ) -> list[dict[str, str]]:
        if period not in _TEAMS_PERIODS:
            raise ValueError(
                f"Unsupported Teams report period: {period}"
            )
        endpoint = (
            "/reports/getTeamsUserActivityUserDetail"
            f"(period='{period}')"
        )
        return self._get_report_csv(endpoint)

    def get_subscribed_skus(self) -> list[dict[str, Any]]:
        return self._get_collection("/subscribedSkus")

    def get_users(self) -> list[dict[str, Any]]:
        return self._get_collection(
            "/users",
            params={
                "$select": (
                    "id,displayName,userPrincipalName,department,jobTitle,"
                    "assignedLicenses"
                ),
                "$top": "999",
            },
        )

    def _get_report_csv(self, endpoint: str) -> list[dict[str, str]]:
        request = Request(
            f"{_GRAPH_BASE_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {self._get_access_token()}",
                "Accept": "text/csv",
            },
        )
        try:
            response = self._graph_opener.open(
                request,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except HTTPError as error:
            if error.code not in _REDIRECT_STATUS_CODES:
                raise
            download_url = error.headers.get("Location")
            if not download_url:
                raise GraphResponseError(
                    "Microsoft Graph returned a report redirect without "
                    "a download URL."
                ) from error
            self._validate_download_url(download_url)
            response = urlopen(
                Request(download_url, headers={"Accept": "text/csv"}),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )

        with response:
            csv_text = response.read().decode("utf-8-sig")

        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise GraphResponseError(
                "Microsoft Graph returned a report without a CSV header."
            )
        return [dict(row) for row in reader]

    def _get_collection(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{_GRAPH_BASE_URL}{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"

        items: list[dict[str, Any]] = []
        while url:
            self._validate_graph_url(url)
            payload = self._get_json(url)
            page_items = payload.get("value")
            if not isinstance(page_items, list):
                raise GraphResponseError(
                    "Microsoft Graph collection response did not contain "
                    "a value list."
                )
            items.extend(page_items)
            next_link = payload.get("@odata.nextLink")
            if next_link is not None and not isinstance(next_link, str):
                raise GraphResponseError(
                    "Microsoft Graph returned an invalid pagination link."
                )
            url = next_link or ""
        return items

    def _get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._get_access_token()}",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise GraphResponseError(
                "Microsoft Graph returned an invalid JSON object."
            )
        return payload

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if (
            self._access_token is not None
            and now < self._token_expires_at - _TOKEN_REFRESH_BUFFER_SECONDS
        ):
            return self._access_token

        tenant_id = quote(self._tenant_id, safe="")
        token_url = (
            "https://login.microsoftonline.com/"
            f"{tenant_id}/oauth2/v2.0/token"
        )
        body = urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = Request(
            token_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))

        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(
            expires_in, (int, float)
        ):
            raise GraphResponseError(
                "Microsoft identity platform returned an invalid token "
                "response."
            )
        self._access_token = access_token
        self._token_expires_at = now + expires_in
        return access_token

    @staticmethod
    def _validate_graph_url(url: str) -> None:
        parsed_url = urlsplit(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc.lower() != "graph.microsoft.com"
        ):
            raise GraphResponseError(
                "Microsoft Graph returned a pagination link outside "
                "graph.microsoft.com."
            )

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed_url = urlsplit(url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise GraphResponseError(
                "Microsoft Graph returned an invalid report download URL."
            )
