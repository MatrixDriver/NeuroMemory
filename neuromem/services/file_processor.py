"""File validation and text extraction."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "txt": "text/plain",
    "py": "text/x-python",
    "js": "text/javascript",
    "ts": "text/typescript",
    "java": "text/x-java",
    "go": "text/x-go",
    "json": "application/json",
    "yaml": "text/yaml",
    "yml": "text/yaml",
    "csv": "text/csv",
    "html": "text/html",
    "css": "text/css",
    "sql": "text/x-sql",
    "sh": "text/x-shellscript",
    "xml": "text/xml",
    "toml": "text/toml",
}

TEXT_EXTENSIONS = {
    "md", "txt", "py", "js", "ts", "java", "go",
    "json", "yaml", "yml", "csv", "html", "css",
    "sql", "sh", "xml", "toml",
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def get_file_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def get_mime_type(filename: str) -> str:
    ext = get_file_extension(filename)
    return ALLOWED_EXTENSIONS.get(ext, "application/octet-stream")


def validate_file(
    filename: str,
    file_size: int,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
) -> tuple[bool, str]:
    """Validate file type and size."""
    ext = get_file_extension(filename)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS.keys()))
        return False, f"Unsupported file type '.{ext}'. Allowed: {allowed}"

    if file_size > max_file_size:
        max_mb = max_file_size // (1024 * 1024)
        return False, f"File too large ({file_size} bytes). Maximum: {max_mb}MB"

    return True, ""


def extract_text(file_data: bytes, file_type: str) -> str | None:
    """Extract text content from file."""
    if file_type in IMAGE_EXTENSIONS:
        return None

    if file_type in TEXT_EXTENSIONS:
        return _extract_text_plain(file_data)

    if file_type == "pdf":
        return _extract_text_pdf(file_data)

    if file_type == "docx":
        return _extract_text_docx(file_data)

    return None


def _extract_text_plain(data: bytes) -> str:
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue
    return data.decode("utf-8", errors="replace")


def _extract_text_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages) if pages else ""
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return ""


def _extract_text_docx(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs) if paragraphs else ""
    except Exception as e:
        logger.warning("DOCX text extraction failed: %s", e)
        return ""
