
from pydantic import BaseModel, Field


class TenderDetails(BaseModel):
    title: str | None = None
    reference: str | None = None
    contracting_authority: str | None = None
    estimated_budget: float | None = None
    currency: str | None = None
    deadline: str | None = None
    provisional_guarantee: str | None = None

    quantity: int | None = Field(default=None, strict=True, ge=1)
    processor: str | None = Field(default=None, min_length=1)
    ram_gb: int | None = Field(default=None, strict=True, ge=1)
    storage_gb: int | None = Field(default=None, strict=True, ge=1)
    screen_size_inches: float | None = Field(
        default=None, strict=True, gt=0
    )
    warranty_months: int | None = Field(default=None, strict=True, ge=0)
    accessories: list[str] = Field(default_factory=list)


class TenderConditionItem(BaseModel):
    condition_type: str
    description: str


class TenderDocumentItem(BaseModel):
    name: str
    description: str | None = None
    is_mandatory: bool = True


class TenderCriterionItem(BaseModel):
    name: str
    description: str | None = None
    weight: float | None = None


class TenderEvidenceItem(BaseModel):
    field_name: str
    extracted_value: str | None = None
    page_number: int | None = None
    source_text: str | None = None


class ExtractionConflictItem(BaseModel):
    field_name: str
    first_value: str | int | float | None = None
    second_value: str | int | float | None = None
    first_chunk_index: int | None = None
    second_chunk_index: int | None = None


class StructuredTenderAnalysis(BaseModel):
    tender: TenderDetails = Field(default_factory=TenderDetails)
    conditions: list[TenderConditionItem] = Field(default_factory=list)
    documents: list[TenderDocumentItem] = Field(default_factory=list)
    criteria: list[TenderCriterionItem] = Field(default_factory=list)
    evidence: list[TenderEvidenceItem] = Field(default_factory=list)
    extraction_conflicts: list[ExtractionConflictItem] = Field(
        default_factory=list
    )
    verified_evidence_count: int = 0
    rejected_evidence_count: int = 0
    corrected_page_count: int = 0
    ambiguous_evidence_count: int = 0


class AnalysisMetadata(BaseModel):
    # Limitation: ``report_truncated`` is set both when the final report is
    # truncated (finish_reason='length') and when a Pass-1 evidence chunk is
    # truncated while building the report. It therefore signals incomplete
    # evidence coverage for the report, not strictly a truncated final report.
    report_truncated: bool = False
    # ``structured_truncated`` is set when the structured JSON output OR a
    # Pass-1 evidence chunk used by structured extraction is truncated.
    structured_truncated: bool = False
    structured_failed: bool = False
    fallback_used: bool = False
    rejected_evidence_count: int = 0
    ambiguous_evidence_count: int = 0
    extraction_conflict_count: int = 0
    degradation_reasons: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    status: str
    model: str
    report: str
    structured_data: StructuredTenderAnalysis | None = None
    metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


class AnalyzeResponse(BaseModel):
    filename: str
    page_count: int
    pages_with_text: int
    analysis: AnalysisResult
    tender_id: int | None = None
