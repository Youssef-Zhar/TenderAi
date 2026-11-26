from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenderInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20)
    estimated_budget: Decimal | None = Field(
        default=None, ge=0, max_digits=24, decimal_places=6
    )
    currency: str | None = Field(default=None, max_length=32)
    deadline: date | None = None
    deadline_time: time | None = None
    deadline_text: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_deadline_time_requires_date(self):
        if self.deadline_time is not None and self.deadline is None:
            raise ValueError("deadline_time requires a deadline date.")
        return self


class TenderCreate(TenderInput):
    pass


class TenderResponse(TenderInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_report: str | None = None
