import io
import shutil

import pymupdf
import pytest

from app.services.pdf_extractor import extract_pdf_pages


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_ocr_extracts_text_from_scanned_pdf():
    image_buffer = io.BytesIO()

    with pymupdf.open() as source:
        source_page = source.new_page(width=595, height=842)
        source_page.insert_text((60, 110), "TENDER NOTICE", fontsize=36)
        source_page.insert_text(
            (60, 170),
            "REFERENCE AO-2026-001",
            fontsize=24,
        )
        pixmap = source_page.get_pixmap(dpi=200)
        image_buffer.write(pixmap.tobytes("png"))

    image_buffer.seek(0)
    pdf_buffer = io.BytesIO()

    with pymupdf.open() as scanned:
        page = scanned.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=image_buffer.getvalue())
        scanned.save(pdf_buffer)

    with pymupdf.open(stream=pdf_buffer.getvalue(), filetype="pdf") as scanned:
        pages, ocr_pages, failed_pages, skipped_pages = extract_pdf_pages(
            scanned,
            ocr_languages="eng",
            ocr_dpi=200,
            ocr_min_text_chars=80,
            ocr_max_pages=5,
        )

    assert pages[0]["text"]
    assert "TENDER" in str(pages[0]["text"]).upper()
    assert ocr_pages == [1]
    assert failed_pages == []
    assert skipped_pages == []
