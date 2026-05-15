from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


@dataclass(frozen=True)
class Assessment:
    name: str
    url: str
    test_type: str
    description: str
    entity_id: str = ""
    job_levels: str = ""
    languages: str = ""
    duration: str = ""
    remote: str = ""
    adaptive: str = ""
    keys: list[str] | None = None

    @property
    def searchable(self) -> str:
        return " ".join(
            [
                self.name,
                self.test_type,
                " ".join(TYPE_LABELS.get(code, code) for code in self.test_type.split()),
                self.description,
                self.job_levels,
                self.languages,
                self.duration,
                self.remote,
                self.adaptive,
                " ".join(self.keys or []),
            ]
        ).lower()

    @property
    def document(self) -> str:
        return (
            f"Name: {self.name}\n"
            f"Test types: {self.test_type} {'; '.join(TYPE_LABELS.get(code, code) for code in self.test_type.split())}\n"
            f"Job levels: {self.job_levels}\n"
            f"Duration: {self.duration}\n"
            f"Languages: {self.languages}\n"
            f"Remote: {self.remote}; Adaptive: {self.adaptive}\n"
            f"Description: {self.description}"
        )


def load_catalog(catalog_path: Path | None = None) -> list[Assessment]:
    path = catalog_path or Path(__file__).parent / "data" / "shl_catalog.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    fields = set(Assessment.__dataclass_fields__)
    return [Assessment(**{k: v for k, v in row.items() if k in fields}) for row in rows]
