"""Load the committed achievement dataset and leader table."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_achievements(path: Path | None = None) -> dict[str, dict]:
    path = path or DATA_DIR / "achievements.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {a["id"].lower(): a for a in raw["achievements"]}


def load_leaders(path: Path | None = None) -> dict[str, dict]:
    path = path or DATA_DIR / "leaders.json"
    return json.loads(path.read_text(encoding="utf-8"))["leaders"]
