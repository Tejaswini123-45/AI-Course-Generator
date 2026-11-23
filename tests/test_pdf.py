import pymupdf
import pytest

from app.services import pdf


def make_pdf(text: str = "", *, encrypted: bool = False) -> bytes:
    with pymupdf.open() as document:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
        if encrypted:
            return document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="test")
        return document.tobytes()


def test_extracts_pdf_text() -> None:
    assert pdf.extract_text(make_pdf("Lists preserve order.")) == "Lists preserve order."


@pytest.mark.parametrize("data", [b"", b"not a PDF"])
def test_rejects_invalid_pdf(data: bytes) -> None:
    with pytest.raises(pdf.PDFError):
        pdf.extract_text(data)


def test_rejects_textless_document() -> None:
    with pytest.raises(pdf.PDFError, match="no extractable text"):
        pdf.extract_text(make_pdf())


def test_rejects_encrypted_document() -> None:
    with pytest.raises(pdf.PDFError, match="Encrypted"):
        pdf.extract_text(make_pdf("Lists", encrypted=True))


def test_checks_file_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf, "MAX_PDF_BYTES", 1)
    with pytest.raises(pdf.PDFSizeError):
        pdf.extract_text(b"too big")
