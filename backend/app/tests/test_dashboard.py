from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.scripts import seed_demo_data as seed_demo_command
from app.services.demo_data import seed_demo_data


@pytest.fixture
def dashboard_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, test_session
    app.dependency_overrides.clear()
    engine.dispose()


def test_dashboard_overview_aggregates_demo_data(dashboard_client) -> None:
    client, test_session = dashboard_client
    with test_session.begin() as db:
        assert seed_demo_data(db) == 8
        assert seed_demo_data(db) == 0

    response = client.get("/api/v1/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["period_start"] == (
        date.today() - timedelta(days=89)
    ).isoformat()
    assert payload["period_end"] == date.today().isoformat()
    assert payload["headcount"] == 8
    assert payload["active_users"] == 6
    assert payload["total_prompts"] == 419
    assert payload["total_meetings"] == 42
    assert payload["data_available"] is True
    seats = payload["license_utilization"]
    assert [seat["tool_name"] for seat in seats] == [
        "Demo Microsoft 365 Copilot",
        "Demo Teams Premium",
    ]
    assert [
        (
            seat["product_category"],
            seat["purchased_seats"],
            seat["consumed_seats"],
            seat["utilization_percent"],
        )
        for seat in seats
    ] == [
        ("paid_copilot", 6, 4, 66.7),
        ("teams_premium", 8, 4, 50.0),
    ]
    assert all(seat["tool_id"] > 0 for seat in seats)


def test_dashboard_overview_returns_empty_metrics_without_data(
    dashboard_client,
) -> None:
    client, _ = dashboard_client

    response = client.get("/api/v1/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["headcount"] == 0
    assert payload["active_users"] == 0
    assert payload["total_prompts"] == 0
    assert payload["total_meetings"] == 0
    assert payload["license_utilization"] == []
    assert payload["data_available"] is False


def test_dashboard_trends_separates_daily_and_period_report_data(
    dashboard_client,
) -> None:
    client, test_session = dashboard_client
    with test_session.begin() as db:
        seed_demo_data(db)

    response = client.get("/api/v1/dashboard/trends")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["daily_prompts"]) == 35
    assert sum(row["prompts"] for row in payload["daily_prompts"]) == 229
    assert payload["copilot_d90"] == {
        "report_refresh_date": date.today().isoformat(),
        "prompts": 190,
        "active_users": 3,
    }
    assert any(
        "not daily history" in limitation
        for limitation in payload["source_limitations"]
    )


def test_department_breakdown_includes_usage_and_copilot_data(
    dashboard_client,
) -> None:
    client, test_session = dashboard_client
    with test_session.begin() as db:
        seed_demo_data(db)

    response = client.get("/api/v1/dashboard/departments")

    assert response.status_code == 200
    assert response.json()["departments"] == [
        {
            "department": "Engineering",
            "headcount": 4,
            "daily_active_users": 2,
            "daily_prompts": 109,
            "copilot_active_users": 2,
            "copilot_prompts": 180,
            "total_prompts": 289,
        },
        {
            "department": "Operations",
            "headcount": 4,
            "daily_active_users": 1,
            "daily_prompts": 120,
            "copilot_active_users": 1,
            "copilot_prompts": 10,
            "total_prompts": 130,
        },
    ]


def test_top_users_ranks_prompt_totals_and_validates_limit(
    dashboard_client,
) -> None:
    client, test_session = dashboard_client
    with test_session.begin() as db:
        seed_demo_data(db)

    response = client.get(
        "/api/v1/dashboard/top-users",
        params={"limit": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 3
    assert [
        (user["display_name"], user["total_prompts"])
        for user in payload["users"]
    ] == [
        ("Demo User 01", 120),
        ("Demo User 06", 120),
        ("Demo User 05", 105),
    ]
    assert payload["users"][0]["copilot_active_days"] == 45
    assert payload["users"][1]["daily_active_days"] == 30

    invalid_response = client.get(
        "/api/v1/dashboard/top-users",
        params={"limit": 0},
    )
    assert invalid_response.status_code == 422


def test_demo_seed_command_refuses_production(monkeypatch) -> None:
    session_factory = Mock()
    monkeypatch.setattr(
        seed_demo_command.settings,
        "ENVIRONMENT",
        "production",
    )
    monkeypatch.setattr(
        seed_demo_command,
        "SessionLocal",
        session_factory,
    )

    with pytest.raises(RuntimeError, match="cannot be seeded"):
        seed_demo_command.main()

    session_factory.begin.assert_not_called()
