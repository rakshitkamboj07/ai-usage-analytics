from datetime import date

from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import UniqueConstraint

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class LicenseInventory(Base):
    __tablename__ = "license_inventory"
    __table_args__ = (
        CheckConstraint(
            "purchased_seats >= 0",
            name="ck_license_inventory_purchased_seats_nonnegative",
        ),
        CheckConstraint(
            "consumed_seats >= 0",
            name="ck_license_inventory_consumed_seats_nonnegative",
        ),
        UniqueConstraint(
            "tool_id",
            "snapshot_date",
            name="uq_license_inventory_tool_snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    tool_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tools.id"),
        nullable=False,
        index=True,
    )

    snapshot_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    purchased_seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    consumed_seats: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
