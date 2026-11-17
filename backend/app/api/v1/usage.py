from datetime import date

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.session import get_db
from app.models.usage_daily import UsageDaily
from app.schemas.usage import UsageDailyRecord, UsageFilters, UsageSummary

router = APIRouter(prefix="/usage", tags=["usage"])


def get_usage_filters(
    start_date: date | None = None,
    end_date: date | None = None,
    tool_id: int | None = None,
    department_id: int | None = None,
) -> UsageFilters:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )
    return UsageFilters(
        start_date=start_date,
        end_date=end_date,
        tool_id=tool_id,
        department_id=department_id,
    )


def _usage_conditions(filters: UsageFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.start_date is not None:
        conditions.append(UsageDaily.usage_date >= filters.start_date)
    if filters.end_date is not None:
        conditions.append(UsageDaily.usage_date <= filters.end_date)
    if filters.tool_id is not None:
        conditions.append(UsageDaily.tool_id == filters.tool_id)
    if filters.department_id is not None:
        conditions.append(UsageDaily.department_id == filters.department_id)
    return conditions


@router.get("/daily", response_model=list[UsageDailyRecord])
def get_daily_usage(
    filters: UsageFilters = Depends(get_usage_filters),
    db: Session = Depends(get_db),
) -> list[UsageDailyRecord]:
    statement = (
        select(
            UsageDaily.usage_date,
            UsageDaily.tool_id,
            UsageDaily.department_id,
            func.sum(UsageDaily.request_count).label("request_count"),
            func.sum(UsageDaily.input_tokens).label("input_tokens"),
            func.sum(UsageDaily.output_tokens).label("output_tokens"),
            func.sum(UsageDaily.cost).label("cost"),
        )
        .where(*_usage_conditions(filters))
        .group_by(
            UsageDaily.usage_date,
            UsageDaily.tool_id,
            UsageDaily.department_id,
        )
        .order_by(UsageDaily.usage_date, UsageDaily.tool_id)
    )
    rows = db.execute(statement).mappings().all()
    return [UsageDailyRecord(**row) for row in rows]


@router.get("/summary", response_model=UsageSummary)
def get_usage_summary(
    filters: UsageFilters = Depends(get_usage_filters),
    db: Session = Depends(get_db),
) -> UsageSummary:
    statement = (
        select(
            func.coalesce(func.sum(UsageDaily.request_count), 0).label(
                "request_count"
            ),
            func.coalesce(func.sum(UsageDaily.input_tokens), 0).label(
                "input_tokens"
            ),
            func.coalesce(func.sum(UsageDaily.output_tokens), 0).label(
                "output_tokens"
            ),
            func.coalesce(func.sum(UsageDaily.cost), Decimal("0")).label(
                "cost"
            ),
        )
        .where(*_usage_conditions(filters))
    )
    totals = db.execute(statement).one()
    return UsageSummary(
        start_date=filters.start_date,
        end_date=filters.end_date,
        tool_id=filters.tool_id,
        department_id=filters.department_id,
        request_count=totals.request_count,
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        cost=totals.cost,
    )
