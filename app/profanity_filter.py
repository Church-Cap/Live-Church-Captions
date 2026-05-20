from __future__ import annotations

import re
from pathlib import Path


# CONTENT WARNING FOR DEVELOPERS:
# The tuple below intentionally contains common profanities so Church Cap can
# mask likely speech-to-text mistakes before captions are shown, translated, or
# saved. Keep this list limited to standalone words that are unlikely to be part
# of normal church vocabulary; broad matching can create confusing false edits.
DEFAULT_BLOCKED_WORDS = (
    "arse",
    "asshole",
    "bastard",
    "bitch",
    "bollocks",
    "bullshit",
    "crap",
    "cunt",
    "damn",
    "dick",
    "douche",
    "fuck",
    "fucking",
    "motherfucker",
    "piss",
    "prick",
    "shit",
    "slut",
    "twat",
    "wanker",
    "whore",
)


class ProfanityFilter:
    """Masks configured words while preserving readable caption flow."""

    def __init__(self, extra_words_path: str | Path = "config/profanity_filter.txt"):
        self.extra_words_path = Path(extra_words_path)
        self._pattern: re.Pattern[str] | None = None
        self.load()

    def load(self) -> None:
        words = set(DEFAULT_BLOCKED_WORDS)
        if self.extra_words_path.exists():
            for line in self.extra_words_path.read_text(encoding="utf-8").splitlines():
                word = line.strip()
                if not word or word.startswith("#"):
                    continue
                words.add(word.lower())

        escaped = sorted((re.escape(word) for word in words if word), key=len, reverse=True)
        if not escaped:
            self._pattern = None
            return
        self._pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(escaped) + r")(?![A-Za-z0-9_])", re.IGNORECASE)

    @staticmethod
    def _mask(match: re.Match[str]) -> str:
        word = match.group(0)
        return "*" * max(3, len(word))

    def apply(self, text: str | None, *, enabled: bool = True) -> str:
        if not text:
            return ""
        if not enabled or self._pattern is None:
            return text
        return self._pattern.sub(self._mask, text)
