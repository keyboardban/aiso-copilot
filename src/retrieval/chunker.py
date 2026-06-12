"""Split a structured page into retrievable chunks.

Chunks follow section boundaries (heading + content) because AI answer engines
retrieve passages, not whole pages. Long sections are split into word-window
chunks; the section heading is prepended to every chunk so that
question-shaped headings keep their retrieval power.
"""

from src.config import CHUNK_MAX_WORDS, CHUNK_TARGET_WORDS
from src.utils.text import split_sentences, word_count


def _pack_blocks(blocks: list, target: int, hard_max: int) -> list:
    """Greedily pack text blocks into chunks near the target word size."""
    chunks = []
    current, current_words = [], 0
    for block in blocks:
        block_words = word_count(block)
        if block_words > hard_max:
            # split an oversized block by sentences
            for sentence_group in _pack_blocks(split_sentences(block), target, hard_max * 4):
                if current_words + word_count(sentence_group) > hard_max and current:
                    chunks.append("\n".join(current))
                    current, current_words = [], 0
                current.append(sentence_group)
                current_words += word_count(sentence_group)
            continue
        if current_words + block_words > hard_max and current:
            chunks.append("\n".join(current))
            current, current_words = [], 0
        current.append(block)
        current_words += block_words
        if current_words >= target:
            chunks.append("\n".join(current))
            current, current_words = [], 0
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_chunks(page: dict) -> list:
    """Return [{"id", "section", "text", "word_count"}, ...]."""
    chunks = []

    def add(section: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        chunks.append(
            {
                "id": len(chunks),
                "section": section or "Introduction",
                "text": text,
                "word_count": word_count(text),
            }
        )

    # page metadata is legitimately retrievable text (title + meta description)
    meta_bits = [page.get("title", ""), page.get("meta_description", "")]
    meta_text = "\n".join(b for b in meta_bits if b)
    if meta_text:
        add("Page metadata", meta_text)

    sections = page.get("sections") or []
    for sec in sections:
        heading = sec.get("heading", "")
        content = sec.get("content", "")
        if not content and not heading:
            continue
        blocks = [line for line in content.splitlines() if line.strip()]
        if not blocks:
            continue
        packed = _pack_blocks(blocks, CHUNK_TARGET_WORDS, CHUNK_MAX_WORDS)
        for piece in packed:
            text = f"{heading}\n{piece}" if heading else piece
            add(heading, text)

    # fallback for unstructured plain text with no sections
    if not chunks and page.get("body_text"):
        paragraphs = [p for p in page["body_text"].splitlines() if p.strip()]
        for piece in _pack_blocks(paragraphs, CHUNK_TARGET_WORDS, CHUNK_MAX_WORDS):
            add("", piece)

    return chunks
