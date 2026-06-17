from __future__ import annotations

import re


_WORD_RE = re.compile(r"\w", re.UNICODE)
_PUNCTUATION_ONLY_RE = re.compile(r"^[\s.·•…\-–—_,;:!?|/\\()\[\]{}\"'`~*+=<>]+$")


def collapse_repeated_phrase(text: str, *, max_phrase_words: int = 18) -> str:
    """Trim obvious Whisper loops like "phrase phrase phrase" to one phrase.

    The guard deliberately requires at least four exact phrase repeats covering
    most of the text so normal rhetorical repetition is left alone.
    """
    words = str(text or "").split()
    if len(words) < 10:
        return str(text or "")

    normalised = [re.sub(r"^[^\w']+|[^\w']+$", "", word.lower()) for word in words]
    best: tuple[int, int, int] | None = None
    max_phrase = min(max_phrase_words, max(1, len(words) // 4))
    for start in range(len(words)):
        for size in range(1, max_phrase + 1):
            if start + size * 4 > len(words):
                continue
            phrase = normalised[start:start + size]
            if not all(phrase):
                continue
            count = 1
            pos = start + size
            while pos + size <= len(words) and normalised[pos:pos + size] == phrase:
                count += 1
                pos += size
            coverage = count * size
            if count >= 4 and coverage >= max(8, int(len(words) * 0.5)):
                if best is None or coverage > best[2]:
                    best = (start, size, coverage)

    if best is None:
        return str(text or "")

    start, size, coverage = best
    repeated_end = start + coverage
    collapsed = words[:start] + words[start:start + size]
    tail = words[repeated_end:]
    if len(tail) <= 8:
        collapsed += tail
    return " ".join(collapsed).strip(" ,.;:-")


def clean_caption_text(text: str) -> str:
    """Return displayable caption text, or empty for punctuation-only noise."""
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    if _PUNCTUATION_ONLY_RE.fullmatch(cleaned):
        return ""
    if not _WORD_RE.search(cleaned):
        return ""
    return cleaned
