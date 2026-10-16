import io

import pytest
from docx import Document

from app.screening.parser import ResumeParseError, UnsupportedResumeFile, extract_text


def pdf_fixture() -> bytes:
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Count 1/Kids[3 0 R]>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/"
        b"Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Length 48>>stream\nBT /F1 12 Tf 40 240 Td (Python Product Manager) Tj ET\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(
        f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(output)


def docx_fixture() -> bytes:
    document = Document()
    document.add_paragraph("Python Product Manager")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def test_extracts_pdf_text():
    file_type, text = extract_text("resume.PDF", pdf_fixture())
    assert file_type == "pdf"
    assert "Python Product Manager" in text


def test_extracts_docx_text():
    file_type, text = extract_text("resume.docx", docx_fixture())
    assert file_type == "docx"
    assert text == "Python Product Manager"


@pytest.mark.parametrize("filename", ["resume.doc", "resume.txt", "resume.xlsx"])
def test_rejects_unsupported_formats(filename):
    with pytest.raises(UnsupportedResumeFile, match="仅支持 PDF 和 DOCX"):
        extract_text(filename, b"content")


def test_rejects_files_over_10mb():
    with pytest.raises(ResumeParseError, match="10MB"):
        extract_text("resume.pdf", b"x" * (10 * 1024 * 1024 + 1))
