from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CopilotUsagePeriod,
    Department,
    License,
    LicenseInventory,
    MeetingDaily,
    Tool,
    UsageDaily,
    User,
)

_DEMO_USERS = (
    ("Demo User 01", "demo.user.01@example.test", "Engineering"),
    ("Demo User 02", "demo.user.02@example.test", "Engineering"),
    ("Demo User 03", "demo.user.03@example.test", "Operations"),
    ("Demo User 04", "demo.user.04@example.test", "Operations"),
    ("Demo User 05", "demo.user.05@example.test", "Engineering"),
    ("Demo User 06", "demo.user.06@example.test", "Operations"),
    ("Demo User 07", "demo.user.07@example.test", "Engineering"),
    ("Demo User 08", "demo.user.08@example.test", "Operations"),
)
_DEMO_MARKER = "demo-v1-user-01"


def seed_demo_data(db: Session) -> int:
    existing_demo_user = db.scalar(
        select(User.id).where(User.aad_object_id == _DEMO_MARKER)
    )
    if existing_demo_user is not None:
        return 0

    departments = {
        "Engineering": Department(name="Demo Engineering"),
        "Operations": Department(name="Demo Operations"),
    }
    db.add_all(departments.values())
    tools = {
        "free_chat": Tool(
            name="Demo Copilot Chat",
            vendor="Demo",
            product_category="free_chat",
        ),
        "paid_copilot": Tool(
            name="Demo Microsoft 365 Copilot",
            vendor="Demo",
            product_category="paid_copilot",
        ),
        "teams_premium": Tool(
            name="Demo Teams Premium",
            vendor="Demo",
            product_category="teams_premium",
        ),
    }
    db.add_all(tools.values())
    users = [
        User(
            aad_object_id=f"demo-v1-user-{index:02d}",
            display_name=name,
            email=email,
            department=department_name,
            job_title="Demo account",
        )
        for index, (name, email, department_name) in enumerate(
            _DEMO_USERS,
            start=1,
        )
    ]
    db.add_all(users)
    db.flush()

    today = date.today()
    report_refresh_date = today
    db.add_all(
        [
            License(
                user_id=users[index].id,
                tool_id=tools["paid_copilot"].id,
                license_type=tools["paid_copilot"].name,
                source="demo",
            )
            for index in range(4)
        ]
    )
    db.add_all(
        [
            License(
                user_id=users[index].id,
                tool_id=tools["teams_premium"].id,
                license_type=tools["teams_premium"].name,
                source="demo",
            )
            for index in range(4)
        ]
    )
    db.add_all(
        [
            LicenseInventory(
                tool_id=tools["paid_copilot"].id,
                snapshot_date=today,
                purchased_seats=6,
                consumed_seats=4,
            ),
            LicenseInventory(
                tool_id=tools["teams_premium"].id,
                snapshot_date=today,
                purchased_seats=8,
                consumed_seats=4,
            ),
        ]
    )

    paid_activity = ((45, 120), (20, 60), (0, 0), (5, 10))
    for index, (active_days, prompts) in enumerate(paid_activity):
        db.add(
            CopilotUsagePeriod(
                user_id=users[index].id,
                period_code="D90",
                report_refresh_date=report_refresh_date,
                prompts_all_apps=prompts,
                prompts_chat_work=0,
                prompts_chat_web=0,
                active_days=active_days,
                app_last_activity={},
            )
        )

    active_day_counts = (35, 30, 2, 0)
    period_start = today - timedelta(days=89)
    for index, active_days in enumerate(active_day_counts, start=4):
        for day_offset in range(90 - active_days, 90):
            usage_date = period_start + timedelta(days=day_offset)
            db.add(
                UsageDaily(
                    user_id=users[index].id,
                    tool_id=tools["free_chat"].id,
                    department_id=departments[
                        _DEMO_USERS[index][2]
                    ].id,
                    usage_date=usage_date,
                    request_count=2 + index % 3,
                    input_tokens=100 + index * 10,
                    output_tokens=150 + index * 10,
                    cost=Decimal("0"),
                )
            )

    for index in range(4):
        for day_offset in range(index, 90, 14):
            db.add(
                MeetingDaily(
                    user_id=users[index].id,
                    tool_id=tools["teams_premium"].id,
                    department_id=departments[_DEMO_USERS[index][2]].id,
                    usage_date=period_start + timedelta(days=day_offset),
                    meeting_count=1 + index % 2,
                )
            )

    return len(users)
