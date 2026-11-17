from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.microsoft_graph import MicrosoftGraphClient
from app.models import (
    CopilotUsagePeriod,
    Department,
    License,
    LicenseInventory,
    TeamsActivityPeriod,
    Tool,
    User,
)

_COPILOT_ACTIVITY_COLUMNS = {
    "copilot_chat_work": "Copilot Chat (work) Last Activity Date",
    "copilot_chat_web": "Copilot Chat (web) Last Activity Date",
    "microsoft_365_copilot": "Microsoft 365 Copilot Last Activity Date",
    "microsoft_teams_copilot": "Microsoft Teams Copilot Last Activity Date",
    "word_copilot": "Word Copilot Last Activity Date",
    "excel_copilot": "Excel Copilot Last Activity Date",
    "powerpoint_copilot": "PowerPoint Copilot Last Activity Date",
    "outlook_copilot": "Outlook Copilot Last Activity Date",
    "onenote_copilot": "OneNote Copilot Last Activity Date",
    "loop_copilot": "Loop Copilot Last Activity Date",
    "edge_copilot": "Edge Last Activity Date",
    "copilot_agent": "Copilot Agent Last Activity Date",
}


class GraphSyncError(ValueError):
    pass


@dataclass(frozen=True)
class GraphSyncResult:
    period_code: str
    directory_users: int
    subscribed_skus: int
    copilot_usage_rows: int
    teams_activity_rows: int


def sync_microsoft_graph(
    db: Session,
    client: MicrosoftGraphClient,
    period_code: str = "D90",
) -> GraphSyncResult:
    directory_users = client.get_users()
    subscribed_skus = client.get_subscribed_skus()
    copilot_rows = client.get_copilot_usage_report(period_code)
    teams_rows = client.get_teams_user_activity_report(period_code)

    _validate_unique(directory_users, "id", "directory users")
    _validate_unique(subscribed_skus, "skuId", "subscribed SKUs")
    _validate_unique(copilot_rows, "User Principal Name", "Copilot report")
    _validate_unique(teams_rows, "User Id", "Teams report")

    with db.begin():
        users_by_id = _sync_users(db, directory_users)
        tools_by_sku = _sync_skus(db, subscribed_skus)
        _sync_license_assignments(
            db,
            directory_users,
            users_by_id,
            tools_by_sku,
        )
        _sync_copilot_report(
            db,
            copilot_rows,
            users_by_id,
            period_code,
        )
        _sync_teams_report(
            db,
            teams_rows,
            users_by_id,
            period_code,
        )

    return GraphSyncResult(
        period_code=period_code,
        directory_users=len(directory_users),
        subscribed_skus=len(subscribed_skus),
        copilot_usage_rows=len(copilot_rows),
        teams_activity_rows=len(teams_rows),
    )


def _validate_unique(
    rows: list[dict[str, Any]],
    key: str,
    source_name: str,
) -> None:
    seen: set[str] = set()
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GraphSyncError(
                f"{source_name} row is missing required field {key!r}."
            )
        normalized = value.strip().casefold()
        if normalized in seen:
            raise GraphSyncError(
                f"{source_name} contains duplicate {key!r} value {value!r}."
            )
        seen.add(normalized)


def _sync_users(
    db: Session,
    graph_users: list[dict[str, Any]],
) -> dict[str, User]:
    users_by_id: dict[str, User] = {}
    departments: dict[str, Department] = {}

    for row in graph_users:
        aad_object_id = _required_string(row, "id", "directory user")
        user_principal_name = _required_string(
            row,
            "userPrincipalName",
            "directory user",
        )
        display_name = (
            _optional_string(row.get("displayName")) or user_principal_name
        )
        department_name = _optional_string(row.get("department"))
        job_title = _optional_string(row.get("jobTitle"))

        user = db.scalar(
            select(User).where(User.aad_object_id == aad_object_id)
        )
        if user is None:
            user = db.scalar(
                select(User).where(
                    User.email.ilike(user_principal_name)
                )
            )
        if user is None:
            user = User(
                aad_object_id=aad_object_id,
                display_name=display_name,
                email=user_principal_name,
                department=department_name,
                job_title=job_title,
            )
            db.add(user)
        else:
            user.aad_object_id = aad_object_id
            user.display_name = display_name
            user.email = user_principal_name
            user.department = department_name
            user.job_title = job_title

        if department_name:
            department = departments.get(department_name.casefold())
            if department is None:
                department = db.scalar(
                    select(Department).where(
                        Department.name.ilike(department_name)
                    )
                )
                if department is None:
                    department = Department(name=department_name)
                    db.add(department)
                departments[department_name.casefold()] = department

        users_by_id[aad_object_id] = user

    db.flush()
    return users_by_id


def _sync_skus(
    db: Session,
    graph_skus: list[dict[str, Any]],
) -> dict[str, Tool]:
    tools_by_sku: dict[str, Tool] = {}
    snapshot_date = date.today()

    for row in graph_skus:
        sku_id = _required_string(row, "skuId", "subscribed SKU")
        sku_part_number = _required_string(
            row,
            "skuPartNumber",
            "subscribed SKU",
        )
        category = _classify_sku(sku_part_number)

        tool = db.scalar(
            select(Tool).where(Tool.graph_sku_id == sku_id)
        )
        if tool is None:
            tool = db.scalar(
                select(Tool).where(Tool.name == sku_part_number)
            )
        if tool is None:
            tool = Tool(
                name=sku_part_number,
                vendor="Microsoft",
                product_category=category,
                graph_sku_id=sku_id,
            )
            db.add(tool)
        else:
            if tool.graph_sku_id not in (None, sku_id):
                raise GraphSyncError(
                    f"Tool {tool.name!r} is already mapped to a different "
                    "Microsoft SKU."
                )
            tool.graph_sku_id = sku_id
            if tool.product_category == "other" and category != "other":
                tool.product_category = category

        prepaid_units = row.get("prepaidUnits")
        if not isinstance(prepaid_units, dict):
            raise GraphSyncError(
                f"Subscribed SKU {sku_part_number!r} is missing prepaidUnits."
            )
        purchased_seats = _nonnegative_integer(
            prepaid_units.get("enabled"),
            f"{sku_part_number}.prepaidUnits.enabled",
        )
        consumed_seats = _nonnegative_integer(
            row.get("consumedUnits"),
            f"{sku_part_number}.consumedUnits",
        )

        db.flush()
        inventory = db.scalar(
            select(LicenseInventory).where(
                LicenseInventory.tool_id == tool.id,
                LicenseInventory.snapshot_date == snapshot_date,
            )
        )
        if inventory is None:
            inventory = LicenseInventory(
                tool_id=tool.id,
                snapshot_date=snapshot_date,
                purchased_seats=purchased_seats,
                consumed_seats=consumed_seats,
            )
            db.add(inventory)
        else:
            inventory.purchased_seats = purchased_seats
            inventory.consumed_seats = consumed_seats
        tools_by_sku[sku_id.casefold()] = tool

    db.flush()
    return tools_by_sku


def _sync_license_assignments(
    db: Session,
    graph_users: list[dict[str, Any]],
    users_by_id: dict[str, User],
    tools_by_sku: dict[str, Tool],
) -> None:
    graph_licenses = db.scalars(
        select(License).where(License.source == "microsoft_graph")
    ).all()
    for license_assignment in graph_licenses:
        license_assignment.is_active = False

    for row in graph_users:
        aad_object_id = _required_string(row, "id", "directory user")
        user = users_by_id[aad_object_id]
        assigned_licenses = row.get("assignedLicenses") or []
        if not isinstance(assigned_licenses, list):
            raise GraphSyncError(
                f"User {aad_object_id!r} has an invalid assignedLicenses list."
            )

        for assignment in assigned_licenses:
            if not isinstance(assignment, dict):
                raise GraphSyncError(
                    f"User {aad_object_id!r} has an invalid license entry."
                )
            sku_id = _required_string(assignment, "skuId", "assigned license")
            tool = tools_by_sku.get(sku_id.casefold())
            if tool is None:
                raise GraphSyncError(
                    f"Assigned SKU {sku_id!r} is missing from subscribedSkus."
                )

            license_assignment = db.scalar(
                select(License).where(
                    License.user_id == user.id,
                    License.tool_id == tool.id,
                    License.source == "microsoft_graph",
                )
            )
            if license_assignment is None:
                db.add(
                    License(
                        user_id=user.id,
                        tool_id=tool.id,
                        license_type=tool.name,
                        source="microsoft_graph",
                        is_active=True,
                    )
                )
            else:
                license_assignment.is_active = True
                license_assignment.license_type = tool.name


def _sync_copilot_report(
    db: Session,
    report_rows: list[dict[str, Any]],
    users_by_id: dict[str, User],
    period_code: str,
) -> None:
    report_tool = _get_or_create_tool(
        db,
        name="Microsoft 365 Copilot",
        product_category="paid_copilot",
    )
    db.flush()
    users_by_email = {
        user.email.casefold(): user for user in users_by_id.values()
    }

    for row in report_rows:
        upn = _required_string(
            row,
            "User Principal Name",
            "Copilot usage report",
        )
        user = users_by_email.get(upn.casefold())
        if user is None:
            raise GraphSyncError(
                f"Copilot report user {upn!r} was not returned by the "
                "directory query. Check report identity visibility."
            )

        report_refresh_date = _required_date(
            row.get("Report Refresh Date"),
            "Copilot report refresh date",
        )
        record = db.scalar(
            select(CopilotUsagePeriod).where(
                CopilotUsagePeriod.user_id == user.id,
                CopilotUsagePeriod.period_code == period_code,
                CopilotUsagePeriod.report_refresh_date
                == report_refresh_date,
            )
        )
        if record is None:
            record = CopilotUsagePeriod(
                user_id=user.id,
                period_code=period_code,
                report_refresh_date=report_refresh_date,
                prompts_all_apps=0,
                prompts_chat_work=0,
                prompts_chat_web=0,
                active_days=0,
            )
            db.add(record)

        record.prompts_all_apps = _report_integer(
            row,
            "Prompts submitted for all apps",
        )
        record.prompts_chat_work = _report_integer(
            row,
            "Prompts submitted for Copilot Chat (work)",
        )
        record.prompts_chat_web = _report_integer(
            row,
            "Prompts submitted for Copilot Chat (web)",
        )
        record.active_days = _report_integer(
            row,
            "Active Usage Days for all apps",
        )
        record.last_activity_date = _optional_date(
            row.get("Last Activity Date"),
            "Copilot last activity date",
        )
        record.app_last_activity = {
            key: _optional_date(
                row.get(column),
                f"Copilot surface activity {column}",
            ).isoformat()
            if _optional_date(
                row.get(column),
                f"Copilot surface activity {column}",
            )
            else None
            for key, column in _COPILOT_ACTIVITY_COLUMNS.items()
        }


def _sync_teams_report(
    db: Session,
    report_rows: list[dict[str, Any]],
    users_by_id: dict[str, User],
    period_code: str,
) -> None:
    teams_tool = _get_or_create_tool(
        db,
        name="Microsoft Teams Activity",
        product_category="other",
    )
    db.flush()
    users_by_upn = {
        user.email.casefold(): user for user in users_by_id.values()
    }

    for row in report_rows:
        aad_object_id = _required_string(
            row,
            "User Id",
            "Teams user activity report",
        )
        user = users_by_id.get(aad_object_id)
        if user is None:
            upn = _optional_string(row.get("User Principal Name"))
            user = users_by_upn.get(upn.casefold()) if upn else None
        if user is None:
            raise GraphSyncError(
                f"Teams report user {aad_object_id!r} was not returned by "
                "the directory query."
            )

        report_refresh_date = _required_date(
            row.get("Report Refresh Date"),
            "Teams report refresh date",
        )
        record = db.scalar(
            select(TeamsActivityPeriod).where(
                TeamsActivityPeriod.user_id == user.id,
                TeamsActivityPeriod.period_code == period_code,
                TeamsActivityPeriod.report_refresh_date
                == report_refresh_date,
            )
        )
        if record is None:
            record = TeamsActivityPeriod(
                user_id=user.id,
                tool_id=teams_tool.id,
                period_code=period_code,
                report_refresh_date=report_refresh_date,
                meeting_count=0,
                meetings_organized=0,
                meetings_attended=0,
                call_count=0,
                team_chat_messages=0,
                private_chat_messages=0,
            )
            db.add(record)

        record.last_activity_date = _optional_date(
            row.get("Last Activity Date"),
            "Teams last activity date",
        )
        record.meeting_count = _report_integer(row, "Meeting Count")
        record.meetings_organized = _report_integer(
            row,
            "Meetings Organized Count",
        )
        record.meetings_attended = _report_integer(
            row,
            "Meetings Attended Count",
        )
        record.call_count = _report_integer(row, "Call Count")
        record.team_chat_messages = _report_integer(
            row,
            "Team Chat Message Count",
        )
        record.private_chat_messages = _report_integer(
            row,
            "Private Chat Message Count",
        )


def _get_or_create_tool(
    db: Session,
    name: str,
    product_category: str,
) -> Tool:
    tool = db.scalar(select(Tool).where(Tool.name == name))
    if tool is None:
        tool = Tool(
            name=name,
            vendor="Microsoft",
            product_category=product_category,
        )
        db.add(tool)
    elif tool.product_category == "other":
        tool.product_category = product_category
    return tool


def _classify_sku(sku_part_number: str) -> str:
    normalized = sku_part_number.casefold().replace(" ", "_")
    if "teams_premium" in normalized:
        return "teams_premium"
    if "copilot" in normalized:
        return "paid_copilot"
    return "other"


def _required_string(
    row: dict[str, Any],
    field: str,
    source_name: str,
) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GraphSyncError(
            f"{source_name} row is missing required field {field!r}."
        )
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _nonnegative_integer(value: Any, field: str) -> int:
    try:
        result = int(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as error:
        raise GraphSyncError(
            f"Microsoft Graph returned an invalid integer for {field}."
        ) from error
    if result < 0:
        raise GraphSyncError(
            f"Microsoft Graph returned a negative value for {field}."
        )
    return result


def _report_integer(row: dict[str, Any], field: str) -> int:
    value = row.get(field)
    if value is None or not str(value).strip():
        return 0
    return _nonnegative_integer(value, field)


def _required_date(value: Any, field: str) -> date:
    parsed = _optional_date(value, field)
    if parsed is None:
        raise GraphSyncError(
            f"Microsoft Graph report is missing {field}."
        )
    return parsed


def _optional_date(value: Any, field: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError as error:
        raise GraphSyncError(
            f"Microsoft Graph returned an invalid date for {field}: "
            f"{normalized!r}."
        ) from error
