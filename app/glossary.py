import csv
import re
from pathlib import Path


class Glossary:
    def __init__(self, path: str | Path = "config/glossary.csv"):
        self.path = Path(path)
        self.replacements: list[tuple[re.Pattern[str], str]] = []
        self.load()

    def load(self) -> None:
        self.replacements.clear()
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                wrong = (row.get("wrong") or "").strip()
                correct = (row.get("correct") or "").strip()
                if not wrong or not correct:
                    continue
                pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
                self.replacements.append((pattern, correct))

    def apply(self, text: str) -> str:
        cleaned = " ".join(text.split())
        for pattern, correct in self.replacements:
            cleaned = pattern.sub(correct, cleaned)
        return cleaned
