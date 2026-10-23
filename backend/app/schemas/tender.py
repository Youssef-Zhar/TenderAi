from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class TenderInput(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20)
    estimated_budget: float | None = Field(default=None, ge=0)
    deadline: date | None = None


class TenderCreate(TenderInput):
    pass


class TenderResponse(TenderInput):
    model_config = ConfigDict(from_attributes=True)

    id: int