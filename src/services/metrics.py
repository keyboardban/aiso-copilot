"""Basic readability metrics for extracted page text."""

import re

from src.utils.text import contains_thai, split_sentences, word_count


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def text_metrics(text: str) -> dict:
    """Word/sentence stats plus Flesch reading ease (English text only)."""
    text = text or ""
    sentences = split_sentences(text)
    words = word_count(text)
    sentence_count = max(1, len(sentences))
    avg_sentence_words = round(words / sentence_count, 1) if words else 0.0
    long_sentences = sum(1 for s in sentences if word_count(s) > 30)

    flesch = None
    note = ""
    latin_words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if contains_thai(text) and len(latin_words) < words * 0.5:
        note = "Readability formula skipped: Flesch applies to English text only."
    elif latin_words:
        syllables = sum(_syllables(w) for w in latin_words)
        flesch = round(
            206.835
            - 1.015 * (len(latin_words) / sentence_count)
            - 84.6 * (syllables / len(latin_words)),
            1,
        )
        flesch = max(0.0, min(100.0, flesch))
        if contains_thai(text):
            note = "Flesch computed on the English portion of mixed-language text."

    return {
        "word_count": words,
        "sentence_count": len(sentences),
        "avg_sentence_words": avg_sentence_words,
        "long_sentence_count": long_sentences,
        "flesch_reading_ease": flesch,
        "note": note,
    }
