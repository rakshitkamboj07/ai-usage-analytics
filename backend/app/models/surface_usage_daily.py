from datetime import date

from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class SurfaceUsageDaily(Base):
    __tablename__ = "surface_usage_daily"
    __table_args__ = (
        CheckConstraint(
            "request_count >= 0",
            name="ck_surface_usage_daily_request_count_nonnegative",
        ),
        UniqueConstraint(
            "user_id",
            "tool_id",
            "usage_date",
            "surface",
            name="uq_surface_usage_daily_user_tool_date_surface",
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

    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    surface: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    request_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
