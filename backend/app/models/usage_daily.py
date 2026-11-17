from datetime import date
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import UniqueConstraint

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    __table_args__ = (
        CheckConstraint(
            "request_count >= 0",
            name="ck_usage_daily_request_count_nonnegative",
        ),
        CheckConstraint(
            "input_tokens >= 0",
            name="ck_usage_daily_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens >= 0",
            name="ck_usage_daily_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "cost >= 0",
            name="ck_usage_daily_cost_nonnegative",
        ),
        UniqueConstraint(
            "user_id",
            "tool_id",
            "usage_date",
            name="uq_usage_daily_user_tool_date",
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

    tool_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tools.id"),
        nullable=False,
        index=True,
    )

    department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id"),
        nullable=True,
        index=True,
    )

    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    request_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
