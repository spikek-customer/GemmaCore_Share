"""Sentence-Aware Deterministic Chunking Module.

Preserves natural semantic boundaries (Japanese punctuation '。', '！', '？',
and newlines) to avoid cutting sentences mid-thought, while tracking locators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class TextSection:
    text: str
    locator: str
    heading: str = ""


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    locator: str
    heading: str
    start_offset: int
    end_offset: int


def prefer_sentence_boundary(text: str, start: int, hard_end: int) -> int:
    """Find a natural sentence or paragraph boundary within the last 35% of chunk."""
    if hard_end >= len(text):
        return len(text)

    # Search window: from start + 65% to hard_end
    lower_bound = start + int((hard_end - start) * 0.65)
    for marker in ("\n\n", "。", "！", "？", ".\n", ". ", "\n"):
        position = text.rfind(marker, lower_bound, hard_end)
        if position >= lower_bound:
            return position + len(marker)

    return hard_end


def chunk_sections(
    sections: Iterable[TextSection],
    chunk_size: int = 500,
    overlap: int = 80,
) -> List[ChunkDraft]:
    """Split structured text sections into overlapping, boundary-aware chunks.

    Args:
        sections: Iterable of TextSection with content and locators.
        chunk_size: Target maximum character length per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of ChunkDraft objects.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be >= 1")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    chunks: List[ChunkDraft] = []
    ordinal = 0
    step = chunk_size - overlap

    for section in sections:
        text = section.text.replace("\x00", "").strip()
        if not text:
            continue

        start = 0
        while start < len(text):
            hard_end = min(start + chunk_size, len(text))
            end = prefer_sentence_boundary(text, start, hard_end)
            if end <= start:
                end = hard_end

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    ChunkDraft(
                        ordinal=ordinal,
                        text=chunk_text,
                        locator=section.locator,
                        heading=section.heading,
                        start_offset=start,
                        end_offset=end,
                    )
                )
                ordinal += 1

            if end >= len(text):
                break
            start = max(start + step, end - overlap)

    return chunks


def chunk_text_sentence_aware(
    text: str,
    chunk_size: int = 500,
    overlap: int = 80,
    locator: str = "",
    heading: str = "",
) -> List[ChunkDraft]:
    """Convenience helper to chunk raw text with sentence awareness."""
    section = TextSection(text=text, locator=locator, heading=heading)
    return chunk_sections([section], chunk_size=chunk_size, overlap=overlap)
