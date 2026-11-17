from datetime import date

from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import UniqueConstraint

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class MeetingDaily(Base):
    __tablename__ = "meeting_daily"
    __table_args__ = (
        CheckConstraint(
            "meeting_count >= 0",
            name="ck_meeting_daily_meeting_count_nonnegative",
        ),
        UniqueConstraint(
            "user_id",
            "tool_id",
            "usage_date",
            name="uq_meeting_daily_user_tool_date",
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

    meeting_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
