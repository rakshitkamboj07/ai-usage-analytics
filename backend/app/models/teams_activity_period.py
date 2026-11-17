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


class TeamsActivityPeriod(Base):
    __tablename__ = "teams_activity_period"
    __table_args__ = (
        CheckConstraint(
            "meeting_count >= 0",
            name="ck_teams_activity_period_meetings_nonnegative",
        ),
        CheckConstraint(
            "meetings_organized >= 0",
            name="ck_teams_activity_period_organized_nonnegative",
        ),
        CheckConstraint(
            "meetings_attended >= 0",
            name="ck_teams_activity_period_attended_nonnegative",
        ),
        UniqueConstraint(
            "user_id",
            "period_code",
            "report_refresh_date",
            name="uq_teams_activity_period_user_window_refresh",
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

    period_code: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    report_refresh_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    last_activity_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    meeting_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    meetings_organized: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    meetings_attended: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    team_chat_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    private_chat_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
