import httpx

from app.core.config import settings


class GraphClient:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    async def get(self, endpoint: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.GRAPH_BASE_URL}/{endpoint}",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
            )
            response.raise_for_status()
            return response.json()
