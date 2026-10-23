from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    estimated_budget: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    deadline: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
