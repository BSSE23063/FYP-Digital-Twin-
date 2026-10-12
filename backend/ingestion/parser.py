"""
Document parser module.
Extracts raw text from PDF, DOCX, TXT, and Markdown files.
"""

from pathlib import Path
import re


def clean_text(text: str) -> str:
    """Normalize whitespace and remove null bytes / control characters."""
    if not text:
        return ""
    # Remove null bytes
    text = text.replace("\x00", "")
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple consecutive newlines (more than 2) to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(file_path: Path) -> str:
    """Extract text from PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    pages = []
    for idx, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            pages.append(page_text.strip())
    return clean_text("\n\n".join(pages))


def parse_docx(file_path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    import docx

    doc = docx.Document(str(file_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return clean_text("\n\n".join(paragraphs))


def parse_text_or_markdown(file_path: Path) -> str:
    """Extract text from plain text or Markdown files."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return clean_text(content)


def parse_document(file_path: Path | str) -> str:
    """
    Parses a document based on its file extension.
    Supported: .pdf, .docx, .txt, .md
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext == ".docx":
        return parse_docx(path)
    elif ext in [".txt", ".md", ".markdown"]:
        return parse_text_or_markdown(path)
    else:
        # Fallback to plain text read
        return parse_text_or_markdown(path)

