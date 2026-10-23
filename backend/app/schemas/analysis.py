"""
app/schemas/analysis.py
------------------------
Pydantic schemas for the PDF analysis response.

The AI analyzer currently returns free-text Markdown.  This schema wraps
that report in a structured envelope that the API can return consistently.
Phase 6 will extend AnalysisResult with structured fields (deadline, budget…).
"""

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """
    Structured envelope for the AI analysis report.

    Fields
    ------
    status : "analysis_completed" | "ocr_required" | "analysis_failed"
    model  : The OpenRouter model identifier that produced the report.
    report : The full analysis text in Markdown / plain text.
    """

    status: str = Field(
        description="Outcome of the analysis attempt.",
        examples=["analysis_completed"],
    )
    model: str = Field(
        description="OpenRouter model used for the analysis.",
    )
    report: str = Field(
        description="Full analysis report produced by the AI model.",
    )


class AnalyzeResponse(BaseModel):
    """
    Full response body returned by POST /api/v1/tenders/analyze-pdf.
    """

    filename: str
    page_count: int
    pages_with_text: int
    analysis: AnalysisResult
