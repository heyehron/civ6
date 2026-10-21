"""Shared application state. Pages read from it and listen to its signals."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, Signal

from .. import config
from ..dataset import DATA_DIR, load_achievements, load_leaders
from ..engine import batch, playbook
from ..state.model import GameState
from ..steam import sync as steam

REPO_PLAYBOOKS = DATA_DIR / "playbooks"


class AppState(QObject):
    sync_changed = Signal()
    selection_changed = Signal()
    dataset_changed = Signal()
    playbooks_changed = Signal()
    game_state_changed = Signal()
    advice_changed = Signal()
    settings_changed = Signal()
    toast = Signal(str, str)  # level, message

    def __init__(self):
        super().__init__()
        self.settings = config.Settings.load()
        self.achievements = load_achievements()
        self.leaders = load_leaders()
        self.unlocked: set[str] = set()
        self.pct: dict[str, float] = {}
        self.synced_at: float | None = None
        self.from_cache = False
        self.selected: list[str] = []
        self.game_state: GameState | None = None
        self.advice: playbook.Advice | None = None
        self.playbooks: dict[str, dict] = {}
        self.manual: dict[str, list[str]] = config.read_json(config.PROGRESS, {})
        self.reload_playbooks()
        cached = steam.load_cache()
        if cached:
            self.apply_sync(cached)
        saved = config.read_json(config.HOME / "selection.json", [])
        self.selected = [s for s in saved if s in self.achievements and s not in self.unlocked]
        self.recompute_advice()

    # Steam ------------------------------------------------------------------------------
    def apply_sync(self, res: steam.SyncResult) -> None:
        self.unlocked, self.pct = set(res.unlocked), dict(res.pct)
        self.synced_at, self.from_cache = res.synced_at, res.from_cache
        newly = [s for s in self.selected if s in self.unlocked]
        if newly:
            self.selected = [s for s in self.selected if s not in self.unlocked]
            names = ", ".join(self.achievements[s]["name"] for s in newly)
            self.toast.emit("success", f"Unlocked since last sync: {names}")
            self.selection_changed.emit()
        self.sync_changed.emit()

    @property
    def locked(self) -> dict[str, dict]:
        return {k: v for k, v in self.achievements.items() if k not in self.unlocked}

    # Selection --------------------------------------------------------------------------
    def selected_achs(self) -> list[dict]:
        return [self.achievements[s] for s in self.selected]

    def set_selected(self, ids: list[str]) -> None:
        self.selected = [i for i in dict.fromkeys(ids) if i in self.achievements]
        config.write_json(config.HOME / "selection.json", self.selected)
        self.selection_changed.emit()
        self.recompute_advice()

    def toggle(self, aid: str) -> list[batch.Conflict]:
        if aid in self.selected:
            self.set_selected([s for s in self.selected if s != aid])
            return []
        conflicts = batch.conflicts_with(self.selected_achs(), self.achievements[aid], self.leaders)
        if not conflicts:
            self.set_selected(self.selected + [aid])
        return conflicts

    def weights(self) -> batch.Weights:
        s = self.settings
        return batch.Weights(s.weight_rarity, s.weight_overlap, s.weight_risk)

    # Dataset edits ----------------------------------------------------------------------
    def update_achievement(self, aid: str, **changes) -> None:
        self.achievements[aid].update(changes)
        path = DATA_DIR / "achievements.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        for a in raw["achievements"]:
            if a["id"].lower() == aid:
                a.update(changes)
        path.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        self.dataset_changed.emit()

    # Playbooks --------------------------------------------------------------------------
    def reload_playbooks(self) -> None:
        pbs = playbook.load_dir(REPO_PLAYBOOKS)
        for k, v in playbook.load_dir(config.USER_PLAYBOOKS).items():
            v["_user"] = True
            pbs[k] = v
        self.playbooks = pbs
        self.playbooks_changed.emit()
        self.recompute_advice()

    def playbook_for(self, aid: str) -> dict:
        return self.playbooks.get(aid) or playbook.auto_playbook(self.achievements[aid], self.leaders)

    def save_playbook(self, pb: dict, to_repo: bool = False) -> None:
        playbook.save(pb, REPO_PLAYBOOKS if to_repo else config.USER_PLAYBOOKS)
        self.reload_playbooks()

    # Game state -------------------------------------------------------------------------
    def set_game_state(self, state: GameState | None) -> None:
        self.game_state = state
        self.game_state_changed.emit()
        try:
            self.recompute_advice()
        except Exception as exc:
            self.toast.emit("error", f"Could not evaluate playbooks on this game state: {type(exc).__name__}: {exc}")

    def game_key(self) -> str:
        return (self.game_state.game_id if self.game_state and self.game_state.game_id else "current")

    def manual_done(self) -> set[str]:
        return set(self.manual.get(self.game_key(), []))

    def set_manual(self, key: str, done: bool) -> None:
        cur = set(self.manual.get(self.game_key(), []))
        cur.add(key) if done else cur.discard(key)
        self.manual[self.game_key()] = sorted(cur)
        config.write_json(config.PROGRESS, self.manual)
        self.recompute_advice()

    def recompute_advice(self) -> None:
        if not self.selected:
            self.advice = None
        else:
            state = self.game_state or GameState()
            pbs = [self.playbook_for(s) for s in self.selected]
            self.advice = playbook.advise(pbs, state, self.manual_done())
        self.advice_changed.emit()

    # Settings ---------------------------------------------------------------------------
    def save_settings(self) -> None:
        self.settings.save()
        self.settings_changed.emit()

    def last_synced_text(self) -> str:
        if not self.synced_at:
            return "Not synced"
        when = time.strftime("%d %b %H:%M", time.localtime(self.synced_at))
        return f"{len(self.unlocked)}/{len(self.achievements)} unlocked · synced {when}" + \
            (" (cached)" if self.from_cache else "")
