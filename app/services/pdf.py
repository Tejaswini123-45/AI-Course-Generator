"""Extract text from a bounded PDF supplied in memory."""

from threading import Lock

import pymupdf

from app.config import MAX_PDF_BYTES, MAX_PDF_PAGES, MAX_TEXT_LENGTH

# PyMuPDF operations must not run concurrently within a process.
_pdf_lock = Lock()


class PDFError(Exception):
    """The uploaded PDF could not be used as a text source."""


class PDFSizeError(PDFError):
    """The PDF exceeds a processing limit."""


def extract_text(data: bytes) -> str:
    if not data:
        raise PDFError("The uploaded PDF is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise PDFSizeError("The PDF exceeds 10 MiB.")

    pages: list[str] = []
    length = 0
    try:
        with _pdf_lock, pymupdf.open(stream=data, filetype="pdf") as document:
            if not document.is_pdf or document.is_repaired:
                raise PDFError("Upload a valid, readable PDF.")
            if document.is_encrypted or document.metadata.get("encryption"):
                raise PDFError("Encrypted PDFs are unsupported.")
            if document.page_count > MAX_PDF_PAGES:
                raise PDFSizeError(f"The PDF exceeds {MAX_PDF_PAGES} pages.")
            for page in document:
                text = page.get_text(sort=True).strip()
                if text:
                    length += len(text) + (2 if pages else 0)
                    if length > MAX_TEXT_LENGTH:
                        raise PDFSizeError(
                            f"The PDF exceeds {MAX_TEXT_LENGTH:,} extracted characters."
                        )
                    pages.append(text)
    except (RuntimeError, ValueError) as exc:
        raise PDFError("The uploaded PDF is invalid or unreadable.") from exc

    if not pages:
        raise PDFError("The PDF contains no extractable text.")
    return "\n\n".join(pages)
