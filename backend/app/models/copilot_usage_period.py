from datetime import date

from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class CopilotUsagePeriod(Base):
    __tablename__ = "copilot_usage_period"
    __table_args__ = (
        CheckConstraint(
            "prompts_all_apps >= 0",
            name="ck_copilot_usage_period_prompts_all_nonnegative",
        ),
        CheckConstraint(
            "prompts_chat_work >= 0",
            name="ck_copilot_usage_period_prompts_work_nonnegative",
        ),
        CheckConstraint(
            "prompts_chat_web >= 0",
            name="ck_copilot_usage_period_prompts_web_nonnegative",
        ),
        CheckConstraint(
            "active_days >= 0",
            name="ck_copilot_usage_period_active_days_nonnegative",
        ),
        UniqueConstraint(
            "user_id",
            "period_code",
            "report_refresh_date",
            name="uq_copilot_usage_period_user_window_refresh",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    period_code: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    report_refresh_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    prompts_all_apps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    prompts_chat_work: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    prompts_chat_web: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    active_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    last_activity_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    app_last_activity: Mapped[dict[str, str | None]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
