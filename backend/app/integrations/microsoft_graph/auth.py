import msal

from app.core.config import settings


class GraphAuth:
    @staticmethod
    def get_access_token() -> str:
        if not all(
            [
                settings.GRAPH_TENANT_ID,
                settings.GRAPH_CLIENT_ID,
                settings.GRAPH_CLIENT_SECRET,
            ]
        ):
            raise ValueError(
                "Microsoft Graph credentials are not configured."
            )

        authority = (
            "https://login.microsoftonline.com/"
            f"{settings.GRAPH_TENANT_ID}"
        )

        app = msal.ConfidentialClientApplication(
            client_id=settings.GRAPH_CLIENT_ID,
            client_credential=settings.GRAPH_CLIENT_SECRET,
            authority=authority,
        )
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(
                "Unable to obtain a Microsoft Graph access token."
            )

        return result["access_token"]
