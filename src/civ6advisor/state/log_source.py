"""Tail Civ VI's Lua.log for CIV6ADV| lines written by the advisor mod (SPEC §4.5)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .model import GameState

MARKER = "CIV6ADV|"


class LogTailer:
    """Pure tail logic, separate from Qt so it can be tested."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.offset = 0
        self.partial = ""
        self.snapshot: dict | None = None
        self.game_id: str | None = None

    def poll(self) -> list[dict]:
        """Read new complete lines and return the parsed CIV6ADV payloads."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:  # file was recreated (new game launch)
            self.offset, self.partial = 0, ""
        if size == self.offset:
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        text = self.partial + chunk
        lines = text.split("\n")
        self.partial = lines.pop()  # unfinished line
        out = []
        for line in lines:
            i = line.find(MARKER)
            if i < 0:
                continue
            try:
                out.append(json.loads(line[i + len(MARKER):].strip()))
            except ValueError:
                continue
        return out

    def apply(self, payloads: list[dict]) -> GameState | None:
        """Merge payloads. A snapshot replaces state; a delta patches it."""
        changed = False
        for p in payloads:
            kind = p.pop("kind", "snapshot")
            gid = str(p.get("game_id", ""))
            if kind == "snapshot":
                if self.snapshot is not None and (gid != self.game_id or p.get("turn", 0) < self.snapshot.get("turn", 0)):
                    self.snapshot = None  # new game or earlier save loaded
                self.snapshot = p
                self.game_id = gid
                changed = True
            elif kind == "delta" and self.snapshot is not None:
                for k, v in p.items():
                    if isinstance(v, list) and isinstance(self.snapshot.get(k), list):
                        self.snapshot[k] = sorted(set(self.snapshot[k]) | set(v))
                    else:
                        self.snapshot[k] = v
                changed = True
        return GameState.from_snapshot(dict(self.snapshot)) if changed and self.snapshot else None


class LogSource(QObject):
    state_changed = Signal(object)  # GameState
    status_changed = Signal(str)

    def __init__(self, path: str, interval_ms: int = 1000, parent=None):
        super().__init__(parent)
        self.tailer = LogTailer(path)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.interval = interval_ms
        self.last_update: float | None = None

    def start(self, from_end: bool = False) -> None:
        if from_end:
            try:
                self.tailer.offset = self.tailer.path.stat().st_size
            except OSError:
                pass
        self.timer.start(self.interval)
        self._tick()

    def stop(self) -> None:
        self.timer.stop()
        self.status_changed.emit("Stopped")

    def _tick(self) -> None:
        if not self.tailer.path.exists():
            self.status_changed.emit(f"{self.tailer.path.name} does not exist at {self.tailer.path}. "
                                     "Press Check setup to find out why.")
            return
        state = self.tailer.apply(self.tailer.poll())
        if state is not None:
            self.last_update = time.time()
            self.state_changed.emit(state)
            self.status_changed.emit(f"Live · turn {state.turn}")
        elif self.last_update is None:
            self.status_changed.emit("Log found but no advisor lines yet. Start or reload a game with the mod "
                                     "enabled; press Check setup if nothing appears.")


class FileSource(QObject):
    """Load a single snapshot JSON file, for demos and testing playbooks."""
    state_changed = Signal(object)
    status_changed = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = Path(path)

    def start(self, from_end: bool = False) -> None:
        try:
            snap = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.status_changed.emit(f"Could not read {self.path.name}: {exc}")
            return
        self.state_changed.emit(GameState.from_snapshot(snap))
        self.status_changed.emit(f"Loaded {self.path.name}")

    def stop(self) -> None:
        pass
