from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import (
    CopilotUsagePeriod,
    License,
    LicenseInventory,
    MeetingDaily,
    Tool,
    UsageDaily,
    User,
)
from app.schemas.recommendation import Recommendation, RecommendationReport

_GRAPH_SOURCE_LIMITATIONS = [
    "Microsoft Graph does not provide the unlicensed Copilot Chat usage report.",
    "Microsoft Graph does not provide Teams Premium feature-level usage.",
]


def build_recommendation_report(
    db: Session,
    start_date: date | None,
    end_date: date | None,
) -> RecommendationReport:
    usage_conditions = []
    if start_date is not None:
        usage_conditions.append(UsageDaily.usage_date >= start_date)
    if end_date is not None:
        usage_conditions.append(UsageDaily.usage_date <= end_date)

    usage_row_count = db.scalar(
        select(func.count()).select_from(UsageDaily).where(*usage_conditions)
    ) or 0
    copilot_period_conditions = [
        CopilotUsagePeriod.period_code == "D90",
    ]
    if end_date is not None:
        copilot_period_conditions.append(
            CopilotUsagePeriod.report_refresh_date <= end_date
        )
    copilot_rows = db.execute(
        select(
            CopilotUsagePeriod.user_id,
            User.display_name,
            CopilotUsagePeriod.active_days,
            CopilotUsagePeriod.prompts_all_apps,
            CopilotUsagePeriod.report_refresh_date,
        )
        .join(User, User.id == CopilotUsagePeriod.user_id)
        .where(*copilot_period_conditions)
        .order_by(CopilotUsagePeriod.report_refresh_date.desc())
    ).all()
    latest_copilot_row_by_user = {}
    for row in copilot_rows:
        latest_copilot_row_by_user.setdefault(row.user_id, row)

    activity = (
        select(
            UsageDaily.user_id.label("user_id"),
            UsageDaily.tool_id.label("tool_id"),
            func.count(func.distinct(UsageDaily.usage_date)).label(
                "active_days"
            ),
            func.coalesce(func.sum(UsageDaily.request_count), 0).label(
                "request_count"
            ),
        )
        .where(*usage_conditions)
        .group_by(UsageDaily.user_id, UsageDaily.tool_id)
        .subquery()
    )

    recommendations: list[Recommendation] = []
    if usage_row_count or latest_copilot_row_by_user:
        graph_idle_users = {
            row.display_name
            for row in latest_copilot_row_by_user.values()
            if row.active_days == 0
        }
        graph_low_use_users = {
            row.display_name
            for row in latest_copilot_row_by_user.values()
            if 0 < row.active_days < 15
        }
        if graph_idle_users:
            recommendations.append(
                Recommendation(
                    code="idle_licenses",
                    title="Review idle Microsoft 365 Copilot licenses",
                    priority="high",
                    rationale=(
                        "These licensed users had no recorded Copilot "
                        "activity in the latest D90 report."
                    ),
                    affected_count=len(graph_idle_users),
                    affected_users=sorted(graph_idle_users),
                    evidence={"active_days": 0, "report_period": "D90"},
                )
            )
        if graph_low_use_users:
            recommendations.append(
                Recommendation(
                    code="low_usage_licenses",
                    title="Coach low-use Microsoft 365 Copilot users",
                    priority="medium",
                    rationale=(
                        "These licensed users were active on fewer than 15 "
                        "days in the latest D90 report."
                    ),
                    affected_count=len(graph_low_use_users),
                    affected_users=sorted(graph_low_use_users),
                    evidence={
                        "active_days_below": 15,
                        "report_period": "D90",
                    },
                )
            )

    if usage_row_count:
        license_rows = db.execute(
            select(
                User.display_name,
                Tool.name.label("tool_name"),
                Tool.product_category,
                func.coalesce(activity.c.active_days, 0).label("active_days"),
            )
            .select_from(License)
            .join(User, User.id == License.user_id)
            .join(Tool, Tool.id == License.tool_id)
            .outerjoin(
                activity,
                and_(
                    activity.c.user_id == License.user_id,
                    activity.c.tool_id == License.tool_id,
                ),
            )
            .where(License.is_active.is_(True))
        ).all()

        idle_by_tool: dict[str, set[str]] = {}
        low_use_by_tool: dict[str, set[str]] = {}
        for row in license_rows:
            if row.product_category in {"free_chat", "teams_premium"}:
                continue
            if (
                latest_copilot_row_by_user
                and row.product_category == "paid_copilot"
            ):
                continue
            if row.active_days == 0:
                idle_by_tool.setdefault(row.tool_name, set()).add(
                    row.display_name
                )
            elif row.active_days < 15:
                low_use_by_tool.setdefault(row.tool_name, set()).add(
                    row.display_name
                )

        for tool_name, names in sorted(idle_by_tool.items()):
            recommendations.append(
                Recommendation(
                    code="idle_licenses",
                    title=f"Review idle {tool_name} licenses",
                    priority="high",
                    rationale=(
                        "These active license assignments had no recorded "
                        "usage in the selected period."
                    ),
                    affected_count=len(names),
                    affected_users=sorted(names),
                    evidence={"active_days": 0},
                )
            )

        for tool_name, names in sorted(low_use_by_tool.items()):
            recommendations.append(
                Recommendation(
                    code="low_usage_licenses",
                    title=f"Coach low-use {tool_name} license holders",
                    priority="medium",
                    rationale=(
                        "These users were active on fewer than 15 days in "
                        "the selected period."
                    ),
                    affected_count=len(names),
                    affected_users=sorted(names),
                    evidence={"active_days_below": 15},
                )
            )

        free_usage_rows = db.execute(
            select(
                User.display_name,
                Tool.name.label("tool_name"),
                activity.c.active_days,
                activity.c.request_count,
            )
            .join(activity, activity.c.user_id == User.id)
            .join(Tool, Tool.id == activity.c.tool_id)
            .where(Tool.product_category == "free_chat")
        ).all()

        power_users: dict[str, set[str]] = {}
        power_user_prompts: dict[str, int] = {}
        total_free_prompts: dict[str, int] = {}
        trial_users: dict[str, set[str]] = {}
        for row in free_usage_rows:
            total_free_prompts[row.tool_name] = (
                total_free_prompts.get(row.tool_name, 0)
                + row.request_count
            )
            if row.active_days >= 30:
                power_users.setdefault(row.tool_name, set()).add(
                    row.display_name
                )
                power_user_prompts[row.tool_name] = (
                    power_user_prompts.get(row.tool_name, 0)
                    + row.request_count
                )
            elif 1 <= row.active_days <= 2:
                trial_users.setdefault(row.tool_name, set()).add(
                    row.display_name
                )

        for tool_name, names in sorted(power_users.items()):
            total_prompts = total_free_prompts[tool_name]
            candidate_prompts = power_user_prompts[tool_name]
            prompt_share = (
                round(candidate_prompts * 100 / total_prompts, 1)
                if total_prompts
                else 0.0
            )
            recommendations.append(
                Recommendation(
                    code="free_power_users",
                    title=f"Evaluate active {tool_name} users for paid seats",
                    priority="low",
                    rationale=(
                        "These free users were active on at least 30 days "
                        "and may benefit from a paid license."
                    ),
                    affected_count=len(names),
                    affected_users=sorted(names),
                    evidence={
                        "active_days_at_least": 30,
                        "prompt_share_percent": prompt_share,
                    },
                )
            )

        for tool_name, names in sorted(trial_users.items()):
            recommendations.append(
                Recommendation(
                    code="trial_users",
                    title=f"Onboard occasional {tool_name} users",
                    priority="low",
                    rationale=(
                        "These free users were active on only one or two "
                        "days in the selected period."
                    ),
                    affected_count=len(names),
                    affected_users=sorted(names),
                    evidence={"active_days_between": "1-2"},
                )
            )

    inventory_conditions = []
    if end_date is not None:
        inventory_conditions.append(
            LicenseInventory.snapshot_date <= end_date
        )
    latest_inventory = (
        select(
            LicenseInventory.tool_id.label("tool_id"),
            func.max(LicenseInventory.snapshot_date).label("snapshot_date"),
        )
        .join(Tool, Tool.id == LicenseInventory.tool_id)
        .where(
            Tool.product_category == "teams_premium",
            *inventory_conditions,
        )
        .group_by(LicenseInventory.tool_id)
        .subquery()
    )
    inventory_rows = db.execute(
        select(
            Tool.id.label("tool_id"),
            Tool.name.label("tool_name"),
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
        .where(Tool.product_category == "teams_premium")
    ).all()

    for inventory in inventory_rows:
        assigned_users = set(
            db.scalars(
                select(License.user_id).where(
                    License.tool_id == inventory.tool_id,
                    License.is_active.is_(True),
                )
            ).all()
        )
        assigned_count = inventory.consumed_seats
        unassigned_count = max(
            inventory.purchased_seats - assigned_count,
            0,
        )

        meeting_conditions = [
            MeetingDaily.tool_id == inventory.tool_id,
            MeetingDaily.meeting_count > 0,
        ]
        if start_date is not None:
            meeting_conditions.append(MeetingDaily.usage_date >= start_date)
        if end_date is not None:
            meeting_conditions.append(MeetingDaily.usage_date <= end_date)
        meeting_rows = db.execute(
            select(
                MeetingDaily.user_id,
                func.sum(MeetingDaily.meeting_count).label("meeting_count"),
            )
            .where(*meeting_conditions)
            .group_by(MeetingDaily.user_id)
        ).all()
        active_meeting_users = {
            row.user_id for row in meeting_rows if row.user_id in assigned_users
        }
        idle_assigned_ids = assigned_users - active_meeting_users
        idle_names = set()
        if idle_assigned_ids and meeting_rows:
            idle_names = set(
                db.scalars(
                    select(User.display_name).where(
                        User.id.in_(idle_assigned_ids)
                    )
                ).all()
            )

        if unassigned_count or idle_names:
            recommendations.append(
                Recommendation(
                    code="right_size_teams_premium",
                    title=f"Review {inventory.tool_name} seat allocation",
                    priority="medium",
                    rationale=(
                        "Compare purchased seats with active assignments and "
                        "meeting activity before renewal."
                    ),
                    affected_count=unassigned_count + len(idle_names),
                    affected_users=sorted(idle_names),
                    evidence={
                        "purchased_seats": inventory.purchased_seats,
                        "assigned_seats": assigned_count,
                        "active_meeting_users": len(active_meeting_users),
                        "unassigned_seats": unassigned_count,
                    },
                )
            )

    inventory_count = db.scalar(
        select(func.count()).select_from(LicenseInventory)
    ) or 0
    return RecommendationReport(
        start_date=start_date,
        end_date=end_date,
        data_available=bool(
            usage_row_count or latest_copilot_row_by_user or inventory_count
        ),
        recommendations=recommendations,
        source_limitations=_GRAPH_SOURCE_LIMITATIONS,
    )
