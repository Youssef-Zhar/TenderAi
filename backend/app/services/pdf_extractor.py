"""PDF text extraction with optional page-level OCR fallback."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_pdf_pages(
    pdf: Any,
    *,
    ocr_languages: str,
    ocr_dpi: int,
    ocr_min_text_chars: int,
    ocr_tessdata: str = "",
    ocr_max_pages: int = 50,
) -> tuple[list[dict[str, str | int]], list[int], list[int], list[int]]:
    """Extract page text and OCR image-heavy pages with sparse native text.

    Returns page records, OCR-success pages, OCR-failure pages, and pages
    skipped after the configured OCR page budget is exhausted. OCR failures
    are isolated so readable native PDF text can still be analysed.
    """
    pages: list[dict[str, str | int]] = []
    ocr_pages: list[int] = []
    ocr_failed_pages: list[int] = []
    ocr_skipped_pages: list[int] = []
    ocr_attempt_count = 0

    for page_index in range(pdf.page_count):
        page_number = page_index + 1
        page = pdf.load_page(page_index)
        page_text = page.get_text("text").strip()

        needs_ocr = len(page_text) < ocr_min_text_chars
        has_visual_content = bool(page.get_images(full=True)) or bool(
            page.get_drawings()
        )

        if needs_ocr and has_visual_content:
            if ocr_attempt_count >= ocr_max_pages:
                ocr_skipped_pages.append(page_number)
                pages.append({"page": page_number, "text": page_text})
                continue

            ocr_attempt_count += 1
            try:
                text_page = page.get_textpage_ocr(
                    language=ocr_languages,
                    dpi=ocr_dpi,
                    full=not bool(page_text),
                    tessdata=ocr_tessdata or None,
                )
                recognized_text = page.get_text(
                    "text",
                    textpage=text_page,
                ).strip()
                if recognized_text:
                    page_text = recognized_text
                    ocr_pages.append(page_number)
            except Exception as exc:
                ocr_failed_pages.append(page_number)
                logger.warning(
                    "OCR failed for PDF page %d (%s).",
                    page_number,
                    type(exc).__name__,
                )

        pages.append({"page": page_number, "text": page_text})

    return pages, ocr_pages, ocr_failed_pages, ocr_skipped_pages
