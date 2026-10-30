from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import get_settings
from app.services import ingestion
from pypdf import PdfWriter


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as stream:
        writer.write(stream)


def test_pdf_pages_keep_original_page_numbers_and_render(tmp_path: Path) -> None:
    document = tmp_path / "blank.pdf"
    _blank_pdf(document)

    assert ingestion._embedded_pdf_pages(document, 2) == [""]
    image = ingestion._render_pdf_page(document, 1)
    try:
        assert image.width > 0 and image.height > 0
    finally:
        image.close()


def test_ocr_configuration_reports_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    previous = settings.ocr_executable_path
    settings.ocr_executable_path = Path("C:/not-a-real-tesseract.exe")
    try:
        with pytest.raises(RuntimeError, match="OCR_EXECUTABLE_NOT_FOUND"):
            ingestion._configure_ocr()
    finally:
        settings.ocr_executable_path = previous


def test_ocr_image_uses_adapter_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import pytesseract

    captured: dict[str, object] = {}
    monkeypatch.setattr(ingestion, "_configure_ocr", lambda: None)
    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        lambda image, timeout: captured.update({"image": image, "timeout": timeout})
        or "  synthetic text  ",
    )

    assert ingestion._ocr_image(object()) == "synthetic text"
    assert captured["timeout"] == get_settings().ocr_timeout_seconds
