"""Heading-aware chunking. Each chunk remembers its page and the nearest
preceding section heading. A heading starts a new chunk (eligibility
criteria are usually one section -- we avoid slicing through it); a chunk
that outgrows the size limit is flushed and the next one starts with the
tail of the previous (overlap), so a sentence cut at a boundary is still
retrievable. Line-based, so it works on PDFs without blank-line breaks."""

import re
from dataclasses import dataclass

from rag.extract import Page
from settings import settings


@dataclass
class Chunk:
    page: int
    section: str | None
    content: str


_HEADING = re.compile(r"^(?:\d+[\.\)]\s+\S.{0,80}|[A-Z][A-Z0-9 &/\-,:()]{3,80}|.{3,80}:)$")


def _is_heading(line: str) -> bool:
    return len(line) <= 90 and bool(_HEADING.match(line))


def chunk_pages(pages: list[Page]) -> list[Chunk]:
    size, overlap = settings.rag_chunk_chars, settings.rag_chunk_overlap_chars
    chunks: list[Chunk] = []
    section: str | None = None

    for page in pages:
        lines: list[str] = []
        length = 0
        has_new_text = False  # False while the buffer holds only carried-over overlap
        chunk_section = section

        def flush(carry_overlap: bool) -> None:
            nonlocal lines, length, has_new_text, chunk_section
            content = "\n".join(lines).strip()
            if content and has_new_text:
                chunks.append(Chunk(page.number, chunk_section, content))
            tail = content[-overlap:] if carry_overlap and has_new_text else ""
            lines, length, has_new_text = ([tail] if tail else []), len(tail), False
            chunk_section = section

        for raw in page.text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if _is_heading(line):
                flush(carry_overlap=False)
                section = line.rstrip(":")
                chunk_section = section
            while len(line) > size:  # a single enormous line (rare)
                lines.append(line[:size])
                has_new_text = True
                flush(carry_overlap=True)
                line = line[size - overlap :]
            lines.append(line)
            length += len(line) + 1
            has_new_text = True
            if length >= size:
                flush(carry_overlap=True)

        flush(carry_overlap=False)

    return chunks
