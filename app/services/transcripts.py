import re
from html import unescape
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_UPLOAD_BYTES = 10_000_000
MAX_TRANSCRIPT_CHARACTERS = 1_000_000
SUPPORTED_TRANSCRIPT_FORMATS = {".txt", ".md", ".pdf", ".docx", ".vtt"}
_VTT_TIMESTAMP = re.compile(
    r"^\s*((?:\d{2,}:)?\d{2}:\d{2}\.\d{3})\s+-->"
)


class TranscriptExtractionError(ValueError):
    pass


class UnsupportedTranscriptFormatError(TranscriptExtractionError):
    pass


def _extract_vtt(content: str) -> str:
    lines = content.lstrip("\ufeff").splitlines()
    cues: list[str] = []
    line_index = 0

    while line_index < len(lines):
        line = lines[line_index].strip()
        if not line or line == "WEBVTT":
            line_index += 1
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            line_index += 1
            while line_index < len(lines) and lines[line_index].strip():
                line_index += 1
            continue

        match = _VTT_TIMESTAMP.match(line)
        if match is None:
            line_index += 1
            continue

        line_index += 1
        cue_lines: list[str] = []
        while line_index < len(lines) and lines[line_index].strip():
            cue_lines.append(lines[line_index].strip())
            line_index += 1
        cue_text = " ".join(cue_lines)
        cue_text = re.sub(
            r"<v(?:\.[^ >]+)?\s+([^>]+)>",
            r"\1: ",
            cue_text,
            flags=re.IGNORECASE,
        )
        cue_text = re.sub(r"<[^>]+>", "", cue_text)
        cue_text = unescape(cue_text).strip()
        if cue_text:
            cues.append(f"{match.group(1)} {cue_text}")

    return "\n".join(cues)


def _extract_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
    except PdfReadError as error:
        raise TranscriptExtractionError("The PDF file could not be read.") from error
    if reader.is_encrypted:
        raise TranscriptExtractionError("Password-protected PDFs are not supported.")
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    try:
        document = Document(BytesIO(content))
    except (BadZipFile, PackageNotFoundError) as error:
        raise TranscriptExtractionError("The DOCX file could not be read.") from error
    parts: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph) and block.text:
            parts.append(block.text)
        elif isinstance(block, Table):
            parts.extend(
                " | ".join(cell.text for cell in row.cells)
                for row in block.rows
            )
    return "\n".join(parts)


def extract_transcript(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_TRANSCRIPT_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_TRANSCRIPT_FORMATS))
        raise UnsupportedTranscriptFormatError(
            f"Unsupported file format. Upload one of: {supported}."
        )

    try:
        if extension in {".txt", ".md"}:
            transcript = content.decode("utf-8-sig")
        elif extension == ".vtt":
            transcript = _extract_vtt(content.decode("utf-8-sig"))
        elif extension == ".pdf":
            transcript = _extract_pdf(content)
        else:
            transcript = _extract_docx(content)
    except UnicodeDecodeError as error:
        raise TranscriptExtractionError(
            "Text transcript files must use UTF-8 encoding."
        ) from error

    transcript = transcript.strip()
    if not transcript:
        raise TranscriptExtractionError(
            "No extractable transcript text was found in the file."
        )
    if len(transcript) > MAX_TRANSCRIPT_CHARACTERS:
        raise TranscriptExtractionError(
            "Extracted transcript text exceeds the 1,000,000-character limit."
        )
    return transcript
