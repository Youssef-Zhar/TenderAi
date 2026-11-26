from app.services.pdf_extractor import extract_pdf_pages


class FakePage:
    def __init__(self, text="", images=None, drawings=None, ocr_text=None, ocr_error=None):
        self.text = text
        self.images = images or []
        self.drawings = drawings or []
        self.ocr_text = ocr_text
        self.ocr_error = ocr_error
        self.ocr_calls = []

    def get_text(self, kind, textpage=None):
        if textpage is not None:
            return textpage
        return self.text

    def get_images(self, full=True):
        return self.images

    def get_drawings(self):
        return self.drawings

    def get_textpage_ocr(self, **kwargs):
        self.ocr_calls.append(kwargs)
        if self.ocr_error:
            raise self.ocr_error
        return self.ocr_text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages
        self.page_count = len(pages)

    def load_page(self, index):
        return self.pages[index]


def extract(pdf):
    return extract_pdf_pages(
        pdf,
        ocr_languages="fra+ara+eng",
        ocr_dpi=250,
        ocr_min_text_chars=80,
        ocr_max_pages=50,
    )


def test_ocr_is_used_for_scanned_image_page():
    page = FakePage(images=[(1,)], ocr_text="Recognized scanned tender text")

    pages, ocr_pages, failed_pages, skipped_pages = extract(FakePdf([page]))

    assert pages == [{"page": 1, "text": "Recognized scanned tender text"}]
    assert ocr_pages == [1]
    assert failed_pages == []
    assert skipped_pages == []
    assert page.ocr_calls[0]["full"] is True
    assert page.ocr_calls[0]["language"] == "fra+ara+eng"
    assert page.ocr_calls[0]["dpi"] == 250


def test_ocr_is_used_for_sparse_native_text_on_image_page():
    page = FakePage(
        text="Short heading",
        images=[(1,)],
        ocr_text="Short heading\nRecognized content from the scanned page",
    )

    pages, ocr_pages, failed_pages = extract(FakePdf([page]))

    assert pages[0]["text"].startswith("Short heading")
    assert ocr_pages == [1]
    assert failed_pages == []
    assert page.ocr_calls[0]["full"] is False


def test_ocr_is_skipped_for_sufficient_native_text():
    page = FakePage(text="A" * 100, images=[(1,)])

    pages, ocr_pages, failed_pages = extract(FakePdf([page]))

    assert pages == [{"page": 1, "text": "A" * 100}]
    assert ocr_pages == []
    assert failed_pages == []
    assert page.ocr_calls == []


def test_ocr_failure_preserves_native_text_and_records_page():
    page = FakePage(
        text="Short native text",
        images=[(1,)],
        ocr_error=RuntimeError("Tesseract is not installed"),
    )

    pages, ocr_pages, failed_pages = extract(FakePdf([page]))

    assert pages == [{"page": 1, "text": "Short native text"}]
    assert ocr_pages == []
    assert failed_pages == [1]
    assert skipped_pages == []



def test_ocr_page_limit_skips_later_pages():
    first = FakePage(images=[(1,)], ocr_text="First scanned page")
    second = FakePage(images=[(2,)], ocr_text="Second scanned page")

    pages, ocr_pages, failed_pages, skipped_pages = extract_pdf_pages(
        FakePdf([first, second]),
        ocr_languages="fra+ara+eng",
        ocr_dpi=250,
        ocr_min_text_chars=80,
        ocr_max_pages=1,
    )

    assert pages == [
        {"page": 1, "text": "First scanned page"},
        {"page": 2, "text": ""},
    ]
    assert ocr_pages == [1]
    assert failed_pages == []
    assert skipped_pages == [2]
    assert second.ocr_calls == []
