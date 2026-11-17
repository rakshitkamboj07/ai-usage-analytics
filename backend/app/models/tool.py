from sqlalchemy import Boolean
from sqlalchemy import Integer
from sqlalchemy import String

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    vendor: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    product_category: Mapped[str] = mapped_column(
        String(50),
        default="other",
        server_default="other",
        nullable=False,
    )

    graph_sku_id: Mapped[str | None] = mapped_column(
        String(36),
        unique=True,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )