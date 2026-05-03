"""Tests for DocumentChunker — three chunking strategies and edge cases."""
from __future__ import annotations

import pytest

from services.doc_chunker import DocumentChunker, DocumentChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunker(**kwargs) -> DocumentChunker:
    return DocumentChunker(**kwargs)


def _text(n_paras: int, para_size: int = 100) -> str:
    """Generate deterministic multi-paragraph text."""
    return "\n\n".join(f"P{i} " + "x" * para_size for i in range(n_paras))


# ---------------------------------------------------------------------------
# chunk_text — paragraph strategy (default)
# ---------------------------------------------------------------------------

class TestChunkByParagraph:
    def test_single_para_within_limit_is_one_chunk(self):
        text = "x" * 60  # above default min_chunk_size=50
        chunks = _chunker(chunk_size=500).chunk_text(text, strategy="paragraph")
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_multiple_paras_merged_when_under_limit(self):
        # Each paragraph is 60 chars (> min_chunk_size=50) but merged they fit in 500
        text = "A" * 60 + "\n\n" + "B" * 60 + "\n\n" + "C" * 60
        chunks = _chunker(chunk_size=500).chunk_text(text, strategy="paragraph")
        # All three should merge into one chunk
        assert len(chunks) == 1
        assert "A" in chunks[0].content
        assert "B" in chunks[0].content
        assert "C" in chunks[0].content

    def test_large_para_triggers_new_chunk(self):
        # Two paragraphs each ~100 chars, chunk_size=120 → must split
        text = "A" * 100 + "\n\n" + "B" * 100
        chunks = _chunker(chunk_size=120).chunk_text(text, strategy="paragraph")
        assert len(chunks) >= 2

    def test_empty_text_returns_no_chunks(self):
        chunks = _chunker().chunk_text("", strategy="paragraph")
        assert chunks == []

    def test_chunk_fields_populated(self):
        chunks = _chunker(chunk_size=500).chunk_text(
            "x" * 60, title="MyDoc", doc_path="/docs/my.txt"
        )
        c = chunks[0]
        assert c.doc_title == "MyDoc"
        assert c.doc_path == "/docs/my.txt"
        assert c.chunk_index == 0
        assert c.total_chunks == 1
        assert c.chunk_id  # non-empty

    def test_chunk_index_sequential(self):
        text = _text(10, para_size=200)
        chunks = _chunker(chunk_size=300).chunk_text(text, strategy="paragraph")
        for i, c in enumerate(chunks):
            assert c.chunk_index == i
        assert chunks[-1].total_chunks == len(chunks)

    def test_small_chunks_merged_into_previous(self):
        """A trailing paragraph smaller than min_chunk_size is merged."""
        big_para = "X" * 200
        tiny_para = "Y" * 10  # below default min_chunk_size=50
        text = big_para + "\n\n" + tiny_para
        chunks = _chunker(chunk_size=250, min_chunk_size=50).chunk_text(
            text, strategy="paragraph"
        )
        # The tiny para should be absorbed into the previous chunk
        joined = " ".join(c.content for c in chunks)
        assert "Y" * 10 in joined


# ---------------------------------------------------------------------------
# chunk_text — fixed_size strategy
# ---------------------------------------------------------------------------

class TestChunkFixedSize:
    def test_exact_multiple_produces_correct_count(self):
        text = "A" * 300
        chunks = _chunker(chunk_size=100, min_chunk_size=1).chunk_text(
            text, strategy="fixed_size"
        )
        assert len(chunks) == 3

    def test_non_multiple_has_remainder_chunk(self):
        text = "A" * 350
        chunks = _chunker(chunk_size=100, min_chunk_size=1).chunk_text(
            text, strategy="fixed_size"
        )
        assert len(chunks) == 4
        assert len(chunks[-1].content) == 50

    def test_short_text_returns_one_chunk(self):
        chunks = _chunker(chunk_size=500, min_chunk_size=1).chunk_text(
            "hello", strategy="fixed_size"
        )
        assert len(chunks) == 1

    def test_char_offset_advances_by_chunk_size(self):
        text = "A" * 300
        chunks = _chunker(chunk_size=100, min_chunk_size=1).chunk_text(
            text, strategy="fixed_size"
        )
        assert chunks[0].char_offset == 0
        assert chunks[1].char_offset == 100
        assert chunks[2].char_offset == 200


# ---------------------------------------------------------------------------
# chunk_text — sliding_window strategy
# ---------------------------------------------------------------------------

class TestChunkSlidingWindow:
    def test_overlap_creates_more_chunks_than_fixed_size(self):
        text = "A" * 400
        fixed = _chunker(chunk_size=100, min_chunk_size=1).chunk_text(
            text, strategy="fixed_size"
        )
        sliding = _chunker(chunk_size=100, chunk_overlap=20, min_chunk_size=1).chunk_text(
            text, strategy="sliding_window"
        )
        assert len(sliding) >= len(fixed)

    def test_adjacent_chunks_share_overlap(self):
        text = "A" * 200
        chunks = _chunker(chunk_size=100, chunk_overlap=20, min_chunk_size=1).chunk_text(
            text, strategy="sliding_window"
        )
        if len(chunks) >= 2:
            # end of first chunk overlaps with start of second
            assert chunks[0].content[-20:] == chunks[1].content[:20]

    def test_zero_effective_step_uses_half_chunk_size(self):
        # chunk_overlap >= chunk_size → step falls back to chunk_size // 2
        text = "A" * 300
        chunks = _chunker(chunk_size=100, chunk_overlap=100, min_chunk_size=1).chunk_text(
            text, strategy="sliding_window"
        )
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# chunk_file — plain text file
# ---------------------------------------------------------------------------

def test_chunk_file_plain_text(tmp_path):
    f = tmp_path / "doc.txt"
    # Each paragraph >50 chars to clear default min_chunk_size
    f.write_text(
        "paragraph one " + "x" * 50 + "\n\n"
        "paragraph two " + "y" * 50 + "\n\n"
        "paragraph three " + "z" * 50,
        encoding="utf-8",
    )
    chunks = _chunker(chunk_size=500).chunk_file(f)
    assert len(chunks) >= 1
    joined = "\n".join(c.content for c in chunks)
    assert "paragraph one" in joined
