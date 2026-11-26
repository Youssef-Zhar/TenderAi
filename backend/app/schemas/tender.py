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



class TenderConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    condition_type: str
    description: str


class TenderDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_mandatory: bool


class TenderCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    weight: float | None = None


class TenderEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field_name: str
    extracted_value: str | None = None
    page_number: int | None = None
    source_text: str | None = None


class TenderDetailResponse(TenderResponse):
    conditions: list[TenderConditionResponse] = Field(default_factory=list)
    documents: list[TenderDocumentResponse] = Field(default_factory=list)
    criteria: list[TenderCriterionResponse] = Field(default_factory=list)
    evidence: list[TenderEvidenceResponse] = Field(default_factory=list)
