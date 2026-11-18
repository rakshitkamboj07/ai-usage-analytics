from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    CopilotUsagePeriod,
    LicenseInventory,
    MeetingDaily,
    TeamsActivityPeriod,
    Tool,
    UsageDaily,
    User,
)
from app.schemas.dashboard import (
    CopilotPeriodSummary,
    DashboardOverview,
    DashboardTopUser,
    DashboardTopUsers,
    DashboardTrends,
    DepartmentBreakdown,
    DepartmentUsage,
    DailyPromptTrend,
    LicenseUtilization,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_TREND_SOURCE_LIMITATIONS = [
    "Microsoft Graph Copilot D90 reports are period aggregates, not daily history.",
]


def _period_window() -> tuple[date, date]:
    period_end = date.today()
    return period_end - timedelta(days=89), period_end


def _latest_copilot_refresh_date(
    db: Session,
    period_end: date,
) -> date | None:
    return db.scalar(
        select(func.max(CopilotUsagePeriod.report_refresh_date)).where(
            CopilotUsagePeriod.period_code == "D90",
            CopilotUsagePeriod.report_refresh_date <= period_end,
        )
    )


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    db: Session = Depends(get_db),
) -> DashboardOverview:
    period_start, period_end = _period_window()
    daily_conditions = [
        UsageDaily.usage_date >= period_start,
        UsageDaily.usage_date <= period_end,
    ]

    headcount = db.scalar(select(func.count()).select_from(User)) or 0
    daily_prompts = db.scalar(
        select(func.coalesce(func.sum(UsageDaily.request_count), 0)).where(
            *daily_conditions
        )
    ) or 0
    daily_active_users = set(
        db.scalars(
            select(UsageDaily.user_id)
            .where(*daily_conditions)
            .distinct()
        ).all()
    )

    copilot_refresh_date = _latest_copilot_refresh_date(db, period_end)
    copilot_prompts = 0
    copilot_active_users: set[int] = set()
    if copilot_refresh_date is not None:
        copilot_rows = db.execute(
            select(
                CopilotUsagePeriod.user_id,
                CopilotUsagePeriod.prompts_all_apps,
                CopilotUsagePeriod.active_days,
            ).where(
                CopilotUsagePeriod.period_code == "D90",
                CopilotUsagePeriod.report_refresh_date
                == copilot_refresh_date,
            )
        ).all()
        copilot_prompts = sum(row.prompts_all_apps for row in copilot_rows)
        copilot_active_users = {
            row.user_id for row in copilot_rows if row.active_days > 0
        }

    teams_refresh_date = db.scalar(
        select(func.max(TeamsActivityPeriod.report_refresh_date)).where(
            TeamsActivityPeriod.period_code == "D90",
            TeamsActivityPeriod.report_refresh_date <= period_end,
        )
    )
    if teams_refresh_date is not None:
        total_meetings = db.scalar(
            select(
                func.coalesce(func.sum(TeamsActivityPeriod.meeting_count), 0)
            ).where(
                TeamsActivityPeriod.period_code == "D90",
                TeamsActivityPeriod.report_refresh_date == teams_refresh_date,
            )
        ) or 0
    else:
        total_meetings = db.scalar(
            select(func.coalesce(func.sum(MeetingDaily.meeting_count), 0)).where(
                MeetingDaily.usage_date >= period_start,
                MeetingDaily.usage_date <= period_end,
            )
        ) or 0

    latest_inventory = (
        select(
            LicenseInventory.tool_id.label("tool_id"),
            func.max(LicenseInventory.snapshot_date).label("snapshot_date"),
        )
        .where(LicenseInventory.snapshot_date <= period_end)
        .group_by(LicenseInventory.tool_id)
        .subquery()
    )
    inventory_rows = db.execute(
        select(
            Tool.id.label("tool_id"),
            Tool.name.label("tool_name"),
            Tool.product_category,
            LicenseInventory.purchased_seats,
            LicenseInventory.consumed_seats,
        )
        .join(LicenseInventory, LicenseInventory.tool_id == Tool.id)
        .join(
            latest_inventory,
            and_(
                latest_inventory.c.tool_id == LicenseInventory.tool_id,
                latest_inventory.c.snapshot_date
                == LicenseInventory.snapshot_date,
            ),
        )
        .where(Tool.product_category.in_(("paid_copilot", "teams_premium")))
        .order_by(Tool.name)
    ).all()
    license_utilization = [
        LicenseUtilization(
            tool_id=row.tool_id,
            tool_name=row.tool_name,
            product_category=row.product_category,
            purchased_seats=row.purchased_seats,
            consumed_seats=row.consumed_seats,
            utilization_percent=(
                round(row.consumed_seats * 100 / row.purchased_seats, 1)
                if row.purchased_seats
                else 0.0
            ),
        )
        for row in inventory_rows
    ]

    active_users = daily_active_users | copilot_active_users
    total_prompts = daily_prompts + copilot_prompts
    return DashboardOverview(
        period_start=period_start,
        period_end=period_end,
        headcount=headcount,
        active_users=len(active_users),
        total_prompts=total_prompts,
        total_meetings=total_meetings,
        license_utilization=license_utilization,
        data_available=bool(
            headcount
            or daily_prompts
            or copilot_prompts
            or total_meetings
            or license_utilization
        ),
    )


@router.get("/trends", response_model=DashboardTrends)
def get_dashboard_trends(
    db: Session = Depends(get_db),
) -> DashboardTrends:
    period_start, period_end = _period_window()
    daily_rows = db.execute(
        select(
            UsageDaily.usage_date,
            Tool.id.label("tool_id"),
            Tool.name.label("tool_name"),
            func.sum(UsageDaily.request_count).label("prompts"),
        )
        .join(Tool, Tool.id == UsageDaily.tool_id)
        .where(
            UsageDaily.usage_date >= period_start,
            UsageDaily.usage_date <= period_end,
        )
        .group_by(UsageDaily.usage_date, Tool.id, Tool.name)
        .order_by(UsageDaily.usage_date, Tool.name)
    ).all()
    daily_prompts = [
        DailyPromptTrend(**row._mapping)
        for row in daily_rows
    ]

    refresh_date = _latest_copilot_refresh_date(db, period_end)
    copilot_summary = None
    if refresh_date is not None:
        rows = db.execute(
            select(
                CopilotUsagePeriod.prompts_all_apps,
                CopilotUsagePeriod.active_days,
            ).where(
                CopilotUsagePeriod.period_code == "D90",
                CopilotUsagePeriod.report_refresh_date == refresh_date,
            )
        ).all()
        copilot_summary = CopilotPeriodSummary(
            report_refresh_date=refresh_date,
            prompts=sum(row.prompts_all_apps for row in rows),
            active_users=sum(row.active_days > 0 for row in rows),
        )

    return DashboardTrends(
        period_start=period_start,
        period_end=period_end,
        daily_prompts=daily_prompts,
        copilot_d90=copilot_summary,
        source_limitations=_TREND_SOURCE_LIMITATIONS,
    )


@router.get("/departments", response_model=DepartmentBreakdown)
def get_department_breakdown(
    db: Session = Depends(get_db),
) -> DepartmentBreakdown:
    period_start, period_end = _period_window()
    department_expression = func.coalesce(User.department, "Unassigned")
    totals: dict[str, dict[str, int]] = {}

    headcount_rows = db.execute(
        select(
            department_expression.label("department"),
            func.count(User.id).label("headcount"),
        ).group_by(department_expression)
    ).all()
    for row in headcount_rows:
        totals[row.department] = {
            "headcount": row.headcount,
            "daily_active_users": 0,
            "daily_prompts": 0,
            "copilot_active_users": 0,
            "copilot_prompts": 0,
        }

    daily_rows = db.execute(
        select(
            department_expression.label("department"),
            func.count(func.distinct(UsageDaily.user_id)).label(
                "active_users"
            ),
            func.sum(UsageDaily.request_count).label("prompts"),
        )
        .join(User, User.id == UsageDaily.user_id)
        .where(
            UsageDaily.usage_date >= period_start,
            UsageDaily.usage_date <= period_end,
        )
        .group_by(department_expression)
    ).all()
    for row in daily_rows:
        bucket = totals.setdefault(
            row.department,
            {
                "headcount": 0,
                "daily_active_users": 0,
                "daily_prompts": 0,
                "copilot_active_users": 0,
                "copilot_prompts": 0,
            },
        )
        bucket["daily_active_users"] = row.active_users
        bucket["daily_prompts"] = row.prompts

    refresh_date = _latest_copilot_refresh_date(db, period_end)
    if refresh_date is not None:
        copilot_rows = db.execute(
            select(
                department_expression.label("department"),
                CopilotUsagePeriod.prompts_all_apps,
                CopilotUsagePeriod.active_days,
            )
            .join(User, User.id == CopilotUsagePeriod.user_id)
            .where(
                CopilotUsagePeriod.period_code == "D90",
                CopilotUsagePeriod.report_refresh_date == refresh_date,
            )
        ).all()
        for row in copilot_rows:
            bucket = totals.setdefault(
                row.department,
                {
                    "headcount": 0,
                    "daily_active_users": 0,
                    "daily_prompts": 0,
                    "copilot_active_users": 0,
                    "copilot_prompts": 0,
                },
            )
            bucket["copilot_prompts"] += row.prompts_all_apps
            bucket["copilot_active_users"] += int(row.active_days > 0)

    departments = [
        DepartmentUsage(
            department=name,
            **metrics,
            total_prompts=(
                metrics["daily_prompts"] + metrics["copilot_prompts"]
            ),
        )
        for name, metrics in sorted(totals.items())
    ]
    return DepartmentBreakdown(
        period_start=period_start,
        period_end=period_end,
        departments=departments,
    )


@router.get("/top-users", response_model=DashboardTopUsers)
def get_top_users(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> DashboardTopUsers:
    period_start, period_end = _period_window()
    users_by_id: dict[int, DashboardTopUser] = {}
    daily_rows = db.execute(
        select(
            User.id.label("user_id"),
            User.display_name,
            User.department,
            func.sum(UsageDaily.request_count).label("prompts"),
            func.count(func.distinct(UsageDaily.usage_date)).label(
                "active_days"
            ),
            func.max(UsageDaily.usage_date).label("last_active_date"),
        )
        .join(UsageDaily, UsageDaily.user_id == User.id)
        .where(
            UsageDaily.usage_date >= period_start,
            UsageDaily.usage_date <= period_end,
        )
        .group_by(User.id, User.display_name, User.department)
    ).all()
    for row in daily_rows:
        users_by_id[row.user_id] = DashboardTopUser(
            user_id=row.user_id,
            display_name=row.display_name,
            department=row.department or "Unassigned",
            daily_prompts=row.prompts,
            copilot_prompts=0,
            total_prompts=row.prompts,
            daily_active_days=row.active_days,
            copilot_active_days=0,
            last_active_date=row.last_active_date,
        )

    refresh_date = _latest_copilot_refresh_date(db, period_end)
    if refresh_date is not None:
        copilot_rows = db.execute(
            select(
                User.id.label("user_id"),
                User.display_name,
                User.department,
                CopilotUsagePeriod.prompts_all_apps,
                CopilotUsagePeriod.active_days,
                CopilotUsagePeriod.last_activity_date,
            )
            .join(User, User.id == CopilotUsagePeriod.user_id)
            .where(
                CopilotUsagePeriod.period_code == "D90",
                CopilotUsagePeriod.report_refresh_date == refresh_date,
            )
        ).all()
        for row in copilot_rows:
            user = users_by_id.get(row.user_id)
            if user is None:
                user = DashboardTopUser(
                    user_id=row.user_id,
                    display_name=row.display_name,
                    department=row.department or "Unassigned",
                    daily_prompts=0,
                    copilot_prompts=0,
                    total_prompts=0,
                    daily_active_days=0,
                    copilot_active_days=0,
                    last_active_date=None,
                )
                users_by_id[row.user_id] = user

            user.copilot_prompts = row.prompts_all_apps
            user.total_prompts = user.daily_prompts + row.prompts_all_apps
            user.copilot_active_days = row.active_days
            if (
                row.last_activity_date is not None
                and (
                    user.last_active_date is None
                    or row.last_activity_date > user.last_active_date
                )
            ):
                user.last_active_date = row.last_activity_date

    top_users = sorted(
        users_by_id.values(),
        key=lambda user: (-user.total_prompts, user.display_name.casefold()),
    )[:limit]
    return DashboardTopUsers(
        period_start=period_start,
        period_end=period_end,
        limit=limit,
        users=top_users,
    )
