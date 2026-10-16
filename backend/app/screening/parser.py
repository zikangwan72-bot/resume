import io
import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

MAX_RESUME_BYTES = 10 * 1024 * 1024


class UnsupportedResumeFile(ValueError):
    """Resume extension is not supported."""


class ResumeParseError(ValueError):
    """Resume content cannot be parsed."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise UnsupportedResumeFile("仅支持 PDF 和 DOCX 文件，暂不支持 DOC 或其它格式")
    if len(content) > MAX_RESUME_BYTES:
        raise ResumeParseError("简历文件不能超过 10MB")
    try:
        if suffix == ".pdf":
            text = " ".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
            )
            file_type = "pdf"
        else:
            document = Document(io.BytesIO(content))
            text = " ".join(paragraph.text for paragraph in document.paragraphs)
            file_type = "docx"
    except Exception as exc:
        raise ResumeParseError("简历文件解析失败，请确认文件未损坏") from exc
    normalized = _normalize(text)
    if not normalized:
        raise ResumeParseError("简历未提取到可用文本")
    return file_type, normalized[:50_000]
