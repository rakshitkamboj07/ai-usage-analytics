from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    CopilotUsagePeriod,
    Department,
    License,
    LicenseInventory,
    TeamsActivityPeriod,
    Tool,
    User,
)
from app.services.microsoft_graph_sync import (
    GraphSyncError,
    sync_microsoft_graph,
)


class FakeMicrosoftGraphClient:
    def __init__(
        self,
        users: list[dict],
        skus: list[dict],
        copilot_rows: list[dict],
        teams_rows: list[dict],
    ) -> None:
        self.users = users
        self.skus = skus
        self.copilot_rows = copilot_rows
        self.teams_rows = teams_rows

    def get_users(self) -> list[dict]:
        return self.users

    def get_subscribed_skus(self) -> list[dict]:
        return self.skus

    def get_copilot_usage_report(self, period: str) -> list[dict]:
        return self.copilot_rows

    def get_teams_user_activity_report(self, period: str) -> list[dict]:
        return self.teams_rows


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine)
    with test_session() as db:
        yield db
    engine.dispose()


@pytest.fixture
def graph_client() -> FakeMicrosoftGraphClient:
    return FakeMicrosoftGraphClient(
        users=[
            {
                "id": "aad-user-1",
                "displayName": "Ada Lovelace",
                "userPrincipalName": "ada@example.test",
                "department": "Engineering",
                "jobTitle": "Analyst",
                "assignedLicenses": [{"skuId": "sku-copilot"}],
            }
        ],
        skus=[
            {
                "skuId": "sku-copilot",
                "skuPartNumber": "M365_COPILOT",
                "prepaidUnits": {"enabled": 12},
                "consumedUnits": 1,
            }
        ],
        copilot_rows=[
            {
                "User Principal Name": "ada@example.test",
                "Report Refresh Date": "11/16/2026",
                "Prompts submitted for all apps": "45",
                "Prompts submitted for Copilot Chat (work)": "10",
                "Prompts submitted for Copilot Chat (web)": "3",
                "Active Usage Days for all apps": "20",
                "Last Activity Date": "11/15/2026",
                "Word Copilot Last Activity Date": "11/14/2026",
            }
        ],
        teams_rows=[
            {
                "User Id": "aad-user-1",
                "User Principal Name": "ada@example.test",
                "Report Refresh Date": "11/16/2026",
                "Last Activity Date": "11/15/2026",
                "Meeting Count": "7",
                "Meetings Organized Count": "2",
                "Meetings Attended Count": "5",
                "Call Count": "3",
                "Team Chat Message Count": "25",
                "Private Chat Message Count": "8",
            }
        ],
    )


def test_sync_persists_graph_reports_and_is_idempotent(
    db_session: Session,
    graph_client: FakeMicrosoftGraphClient,
) -> None:
    first_result = sync_microsoft_graph(db_session, graph_client)
    second_result = sync_microsoft_graph(db_session, graph_client)

    assert first_result.period_code == "D90"
    assert first_result.directory_users == 1
    assert first_result.subscribed_skus == 1
    assert first_result.copilot_usage_rows == 1
    assert first_result.teams_activity_rows == 1
    assert second_result == first_result

    user = db_session.scalar(select(User))
    assert user is not None
    assert user.display_name == "Ada Lovelace"
    assert user.department == "Engineering"
    assert db_session.scalar(select(func.count()).select_from(Department)) == 1

    copilot = db_session.scalar(select(CopilotUsagePeriod))
    assert copilot is not None
    assert copilot.prompts_all_apps == 45
    assert copilot.prompts_chat_work == 10
    assert copilot.prompts_chat_web == 3
    assert copilot.active_days == 20
    assert copilot.last_activity_date == date(2026, 11, 15)
    assert copilot.app_last_activity["word_copilot"] == "2026-11-14"

    teams = db_session.scalar(select(TeamsActivityPeriod))
    assert teams is not None
    assert teams.meeting_count == 7
    assert teams.meetings_organized == 2
    assert teams.meetings_attended == 5
    assert teams.call_count == 3
    assert teams.team_chat_messages == 25
    assert teams.private_chat_messages == 8

    tool = db_session.scalar(
        select(Tool).where(Tool.graph_sku_id == "sku-copilot")
    )
    assert tool is not None
    assert tool.product_category == "paid_copilot"
    assert db_session.scalar(select(func.count()).select_from(License)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(LicenseInventory))
        == 1
    )


def test_sync_rolls_back_when_report_user_is_not_in_directory(
    db_session: Session,
    graph_client: FakeMicrosoftGraphClient,
) -> None:
    graph_client.copilot_rows[0]["User Principal Name"] = "missing@example.test"

    with pytest.raises(GraphSyncError, match="was not returned by the directory"):
        sync_microsoft_graph(db_session, graph_client)

    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    assert db_session.scalar(select(func.count()).select_from(Tool)) == 0
    assert (
        db_session.scalar(select(func.count()).select_from(LicenseInventory))
        == 0
    )
