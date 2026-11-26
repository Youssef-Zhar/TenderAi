from datetime import date, time
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_budget: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    deadline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
