"""User settings and local storage paths. Nothing here is committed to git."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("CIV6ADVISOR_HOME", Path.home() / ".civ6advisor"))
ICON_DIR = HOME / "assets" / "icons"
BATCHES = HOME / "batches.json"
PROGRESS = HOME / "progress.json"
USER_PLAYBOOKS = HOME / "playbooks"
SETTINGS = HOME / "config.json"


def civ_dir_candidates() -> list[Path]:
    """Where 'My Games/Sid Meier's Civilization VI' may live. Documents is often redirected to OneDrive."""
    home = Path.home()
    bases = [home / "Documents", home / "OneDrive" / "Documents", home / "OneDrive - Personal" / "Documents"]
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(env):
            bases.append(Path(os.environ[env]) / "Documents")
    seen, out = set(), []
    for b in bases:
        p = b / "My Games" / "Sid Meier's Civilization VI"
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find_civ_dir() -> Path | None:
    return next((p for p in civ_dir_candidates() if p.exists()), None)


def default_lua_log() -> str:
    base = find_civ_dir() or civ_dir_candidates()[0]
    return str(base / "Logs" / "Lua.log")


@dataclass
class Settings:
    profile: str = ""
    lua_log: str = field(default_factory=default_lua_log)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:3b"
    temperature: float = 0.4
    max_difficulty: str = "emperor"
    weight_rarity: float = 1.0
    weight_overlap: float = 1.5
    weight_risk: float = 0.5
    hud_screen: int = -1  # -1 = first non-primary screen
    hud_opacity: float = 0.92
    hud_geometry: list = field(default_factory=list)  # [x, y, w, h] remembered between runs
    show_scenarios: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
