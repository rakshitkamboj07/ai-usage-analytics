from datetime import date
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Department,
    License,
    LicenseInventory,
    MeetingDaily,
    Tool,
    UsageDaily,
    User,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def use_test_database():
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
    yield
    app.dependency_overrides.clear()
    engine.dispose()


def test_root_returns_api_message() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "AI Usage Analytics API Running"}


def test_legacy_health_endpoint_remains_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_versioned_health_endpoint_is_available() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_swagger_docs_remain_available() -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text


def test_usage_endpoints_are_documented() -> None:
    openapi = client.get("/openapi.json").json()

    assert "/api/v1/usage/daily" in openapi["paths"]
    assert "/api/v1/usage/summary" in openapi["paths"]
    assert "/api/v1/recommendations" in openapi["paths"]
    assert "UsageDailyRecord" in openapi["components"]["schemas"]
    assert "UsageSummary" in openapi["components"]["schemas"]


def test_usage_filters_reject_reversed_date_range() -> None:
    response = client.get(
        "/api/v1/usage/daily",
        params={"start_date": "2026-01-02", "end_date": "2026-01-01"},
    )

    assert response.status_code == 422


def test_usage_daily_returns_empty_list_when_no_data_exists() -> None:
    response = client.get(
        "/api/v1/usage/daily",
        params={"start_date": "2026-01-01"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_usage_endpoints_aggregate_daily_records() -> None:
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        department = Department(name="Engineering")
        tool = Tool(name="M365 Copilot", vendor="Microsoft")
        user_one = User(
            aad_object_id="user-1",
            display_name="User One",
            email="user1@example.test",
        )
        user_two = User(
            aad_object_id="user-2",
            display_name="User Two",
            email="user2@example.test",
        )
        db.add_all([department, tool, user_one, user_two])
        db.flush()
        db.add_all(
            [
                UsageDaily(
                    user_id=user_one.id,
                    tool_id=tool.id,
                    department_id=department.id,
                    usage_date=date(2025, 12, 1),
                    request_count=3,
                    input_tokens=100,
                    output_tokens=200,
                    cost=Decimal("1.250000"),
                ),
                UsageDaily(
                    user_id=user_two.id,
                    tool_id=tool.id,
                    department_id=department.id,
                    usage_date=date(2025, 12, 1),
                    request_count=4,
                    input_tokens=150,
                    output_tokens=250,
                    cost=Decimal("2.500000"),
                ),
            ]
        )
        db.commit()
        tool_id = tool.id
        department_id = department.id
    finally:
        db_generator.close()

    daily_response = client.get(
        "/api/v1/usage/daily",
        params={"start_date": "2025-12-01", "tool_id": tool_id},
    )
    assert daily_response.status_code == 200
    assert daily_response.json() == [
        {
            "usage_date": "2025-12-01",
            "tool_id": tool_id,
            "department_id": department_id,
            "request_count": 7,
            "input_tokens": 250,
            "output_tokens": 450,
            "cost": "3.750000",
        }
    ]

    summary_response = client.get(
        "/api/v1/usage/summary",
        params={"tool_id": tool_id, "department_id": department_id},
    )
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "start_date": None,
        "end_date": None,
        "tool_id": tool_id,
        "department_id": department_id,
        "request_count": 7,
        "input_tokens": 250,
        "output_tokens": 450,
        "cost": "3.750000",
    }


def test_recommendations_report_no_data_without_usage_or_inventory() -> None:
    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    assert response.json() == {
        "start_date": None,
        "end_date": None,
        "data_available": False,
        "recommendations": [],
        "source_limitations": [
            "Microsoft Graph does not provide the unlicensed Copilot Chat usage report.",
            "Microsoft Graph does not provide Teams Premium feature-level usage.",
        ],
    }


def test_recommendations_identify_idle_and_low_use_licenses() -> None:
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        paid_tool = Tool(
            name="M365 Copilot",
            vendor="Microsoft",
            product_category="paid_copilot",
        )
        free_tool = Tool(
            name="Copilot Chat",
            vendor="Microsoft",
            product_category="free_chat",
        )
        teams_tool = Tool(
            name="Teams Premium",
            vendor="Microsoft",
            product_category="teams_premium",
        )
        idle_user = User(
            aad_object_id="idle-user",
            display_name="Idle User",
            email="idle@example.test",
        )
        low_use_user = User(
            aad_object_id="low-use-user",
            display_name="Low Use User",
            email="low-use@example.test",
        )
        active_free_user = User(
            aad_object_id="active-free-user",
            display_name="Active Free User",
            email="active-free@example.test",
        )
        teams_user = User(
            aad_object_id="teams-user",
            display_name="Teams User",
            email="teams@example.test",
        )
        db.add_all(
            [
                paid_tool,
                free_tool,
                teams_tool,
                idle_user,
                low_use_user,
                active_free_user,
                teams_user,
            ]
        )
        db.flush()
        db.add_all(
            [
                License(
                    user_id=idle_user.id,
                    tool_id=paid_tool.id,
                    license_type="M365 Copilot",
                ),
                License(
                    user_id=low_use_user.id,
                    tool_id=paid_tool.id,
                    license_type="M365 Copilot",
                ),
                License(
                    user_id=teams_user.id,
                    tool_id=teams_tool.id,
                    license_type="Teams Premium",
                ),
                LicenseInventory(
                    tool_id=teams_tool.id,
                    snapshot_date=date(2025, 12, 30),
                    purchased_seats=2,
                    consumed_seats=1,
                ),
                UsageDaily(
                    user_id=low_use_user.id,
                    tool_id=paid_tool.id,
                    usage_date=date(2025, 12, 1),
                    request_count=2,
                    input_tokens=10,
                    output_tokens=20,
                    cost=Decimal("0.010000"),
                ),
            ]
        )
        db.add_all(
            [
                UsageDaily(
                    user_id=active_free_user.id,
                    tool_id=free_tool.id,
                    usage_date=date(2025, 10, 1) + timedelta(days=day),
                    request_count=1,
                    input_tokens=10,
                    output_tokens=20,
                    cost=Decimal("0.000000"),
                )
                for day in range(30)
            ]
        )
        db.add(
            MeetingDaily(
                user_id=teams_user.id,
                tool_id=teams_tool.id,
                usage_date=date(2025, 12, 1),
                meeting_count=1,
            )
        )
        db.commit()
    finally:
        db_generator.close()

    response = client.get(
        "/api/v1/recommendations",
        params={"start_date": "2025-09-30", "end_date": "2025-12-30"},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["data_available"] is True
    recommendations = {
        item["code"]: item for item in report["recommendations"]
    }
    assert recommendations["idle_licenses"]["affected_users"] == [
        "Idle User"
    ]
    assert recommendations["low_usage_licenses"]["affected_users"] == [
        "Low Use User"
    ]
    assert recommendations["free_power_users"]["affected_users"] == [
        "Active Free User"
    ]
    assert recommendations["right_size_teams_premium"]["evidence"][
        "unassigned_seats"
    ] == 1
