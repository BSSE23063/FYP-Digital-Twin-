"""
Chunking module.
Splits text into chunks with character offsets (char_start, char_end) for gold-span evaluation.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    heading_path: str | None = None


class FixedTokenChunker:
    """
    Splits text into chunks using word-based approximation with overlap.
    Tracks exact character offsets (char_start, char_end) inside original text.
    """

    def __init__(self, target_chunk_size: int = 512, overlap: int = 50):
        # target_chunk_size is in tokens (approximated as words or whitespace tokens)
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, heading_path: str | None = None) -> List[TextChunk]:
        if not text or not text.strip():
            return []

        # Find words and their character start/end spans
        import re
        words_matches = list(re.finditer(r"\S+", text))
        if not words_matches:
            return []

        chunks: List[TextChunk] = []
        total_words = len(words_matches)
        start_word_idx = 0
        chunk_idx = 0

        step = max(1, self.target_chunk_size - self.overlap)

        while start_word_idx < total_words:
            end_word_idx = min(start_word_idx + self.target_chunk_size, total_words)

            char_start = words_matches[start_word_idx].start()
            char_end = words_matches[end_word_idx - 1].end()
            chunk_content = text[char_start:char_end].strip()

            chunks.append(
                TextChunk(
                    chunk_index=chunk_idx,
                    content=chunk_content,
                    char_start=char_start,
                    char_end=char_end,
                    heading_path=heading_path,
                )
            )
            chunk_idx += 1

            if end_word_idx >= total_words:
                break

            start_word_idx += step

        return chunks

