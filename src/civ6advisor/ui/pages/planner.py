"""Planner page: the current batch, its lobby checklist, suggested batches and saved batches."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ... import config
from ...engine import batch, planner
from ..appstate import AppState
from ..theme import C, LABEL_COLOURS, rarity_colour
from ..widgets import Badge, Card, EmptyState, FlowLayout, IconCache, PageHeader, button, label, placeholder_icon


class TargetRow(QWidget):
    def __init__(self, app: AppState, icons: IconCache, aid: str, on_open):
        super().__init__()
        a = app.achievements[aid]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        ic = QLabel()
        pm = icons.get(aid, a.get("icon")) or placeholder_icon(28, a["name"])
        ic.setPixmap(pm.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        ic.setFixedSize(30, 30)
        lay.addWidget(ic)
        name = button(a["name"], "Ghost", tip=a["description"], slot=lambda: on_open(aid))
        name.setStyleSheet(f"text-align: left; color: {C['text']};")
        lay.addWidget(name, 1)
        pct = app.pct.get(aid)
        if pct is not None:
            lay.addWidget(Badge(f"{pct:.1f}%", rarity_colour(pct)))
        if aid in app.playbooks:
            lay.addWidget(Badge("playbook", C["blue"]))
        rm = button("✕", "Ghost", tip="Remove from batch", slot=lambda: app.toggle(aid))
        rm.setFixedWidth(30)
        lay.addWidget(rm)


class SuggestionCard(Card):
    def __init__(self, app: AppState, s: planner.Suggestion, rank: int, on_use):
        super().__init__()
        self.body.addWidget(label(f"#{rank}  {s.anchor}", "Big", wrap=True))
        top = FlowLayout()
        top.addWidget(Badge(f"value {s.score:.1f}", C["gold"], filled=True))
        top.addWidget(Badge(f"rarity {s.rarity:.0f}", C["purple"]))
        top.addWidget(Badge(f"effort ~{s.effort:.1f}", C["muted"]))
        top.addWidget(Badge(f"{len(s.ids)} achievements", C["blue"]))
        self.body.addLayout(top)
        names = []
        for i in s.ids:
            a = app.achievements[i]
            pct = app.pct.get(i)
            names.append(f"<span style='color:{rarity_colour(pct)}'>{a['name']}</span>"
                         f"<span style='color:{C['faint']}'> {'' if pct is None else f'{pct:.1f}%'}</span>")
        text = label(" · ".join(names), wrap=True)
        text.setTextFormat(Qt.RichText)
        self.body.addWidget(text)
        for w in s.warnings:
            wl = label("⚠ " + w, wrap=True)
            wl.setStyleSheet(f"color: {C['amber']}; background: transparent;")
            self.body.addWidget(wl)
        row = QHBoxLayout()
        row.addWidget(label("Effort is a heuristic estimate (unverified).", "Faint", wrap=True), 1)
        row.addWidget(button("Use this batch", "Primary", slot=lambda: on_use(s.ids)))
        self.body.addLayout(row)


class SuggestionList(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.lay = QVBoxLayout(self.host)
        self.lay.setContentsMargins(0, 8, 6, 8)
        self.lay.setSpacing(10)
        self.setWidget(self.host)

    def set_cards(self, cards: list[QWidget]) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in cards:
            self.lay.addWidget(c)
        self.lay.addStretch(1)


class PlannerPage(QWidget):
    open_achievement = Signal(str)
    start_game = Signal()

    def __init__(self, app: AppState, icons: IconCache):
        super().__init__()
        self.app, self.icons = app, icons
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.header = PageHeader("Batch planner", "Build one game's worth of achievements, then set up the lobby.")
        self.saved_combo = QComboBox()
        self.saved_combo.setMinimumWidth(200)
        self.saved_combo.activated.connect(self._load_saved)
        self.header.actions.addWidget(self.saved_combo)
        self.header.actions.addWidget(button("Save batch", slot=self._save))
        self.start_btn = button("Start game  →", "Primary", slot=self.start_game.emit)
        self.header.actions.addWidget(self.start_btn)
        lay.addWidget(self.header)

        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(12)

        self.batch_card = Card("Targets")
        self.targets = QVBoxLayout()
        self.targets.setSpacing(2)
        self.batch_card.body.addLayout(self.targets)
        self.stats = label("", "Muted", wrap=True)
        self.stats.setTextFormat(Qt.RichText)
        self.batch_card.body.addWidget(self.stats)
        brow = QHBoxLayout()
        brow.addWidget(button("Clear", "Ghost", slot=lambda: app.set_selected([])))
        brow.addStretch(1)
        self.batch_card.body.addLayout(brow)
        lv.addWidget(self.batch_card)

        check_card = Card("Lobby checklist")
        self.check = QTableWidget(0, 4)
        self.check.setHorizontalHeaderLabels(["Setting", "Value", "", "Because of"])
        self.check.verticalHeader().setVisible(False)
        self.check.setEditTriggers(QTableWidget.NoEditTriggers)
        self.check.setSelectionMode(QTableWidget.NoSelection)
        self.check.setShowGrid(False)
        self.check.setWordWrap(True)
        ch = self.check.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(1, QHeaderView.Stretch)
        ch.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(3, QHeaderView.Stretch)
        check_card.body.addWidget(self.check, 1)
        crow = QHBoxLayout()
        crow.addWidget(label("Required = forced by a target · Recommended = makes it easier · Free = your call",
                             "Faint"), 1)
        crow.addWidget(button("Copy as text", slot=self._copy))
        check_card.body.addLayout(crow)
        lv.addWidget(check_card, 1)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        tools = QHBoxLayout()
        tools.addWidget(label("Suggested batches", "SectionTitle"), 1)
        tools.addWidget(label("Max difficulty", "Muted"))
        self.max_diff = QComboBox()
        self.max_diff.addItems([d.title() for d in batch.DIFFICULTIES])
        self.max_diff.setCurrentText(app.settings.max_difficulty.title())
        self.max_diff.currentTextChanged.connect(self._max_diff_changed)
        tools.addWidget(self.max_diff)
        tools.addWidget(button("Generate", "Primary", slot=self.generate))
        rv.addLayout(tools)
        self.tabs = QTabWidget()
        self.best = SuggestionList()
        self.season = SuggestionList()
        self.tabs.addTab(self.best, "Best next game")
        self.tabs.addTab(self.season, "Season plan (no overlap)")
        rv.addWidget(self.tabs, 1)
        self.best.set_cards([EmptyState("No suggestions yet", "Press Generate to build batches from your locked "
                                                              "achievements.")])
        self.season.set_cards([EmptyState("No plan yet", "Press Generate.")])
        split.addWidget(right)
        split.setSizes([620, 680])
        lay.addWidget(split, 1)

        app.selection_changed.connect(self.refresh)
        app.sync_changed.connect(self.refresh)
        self._reload_saved()
        self.refresh()

    # Batch view -------------------------------------------------------------------------
    def refresh(self) -> None:
        app = self.app
        while self.targets.count():
            it = self.targets.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        sel = app.selected_achs()
        if not sel:
            self.targets.addWidget(label("No targets yet. Tick achievements on the Achievements page or use a "
                                         "suggestion.", "Muted", wrap=True))
        for a in sel:
            self.targets.addWidget(TargetRow(app, self.icons, a["id"], self.open_achievement.emit))
        self.start_btn.setEnabled(bool(sel))
        if sel:
            r = sum(planner.rarity(app.pct.get(a["id"])) for a in sel)
            e = planner.estimate_effort(sel, app.leaders)
            warns = planner.warnings(sel, app.leaders)
            html = (f"Rarity <b style='color:{C['purple']}'>{r:.1f}</b> · effort ~<b>{e:.1f}</b> · value "
                    f"<b style='color:{C['gold_hi']}'>{r / e:.1f}</b>")
            html += "".join(f"<br><span style='color:{C['amber']}'>⚠ {w}</span>" for w in warns)
            self.stats.setText(html)
        else:
            self.stats.setText("")

        items = batch.lobby_checklist(sel, app.leaders) if sel else []
        self.check.setRowCount(len(items))
        for r, it in enumerate(items):
            names = [app.achievements[s]["name"] if s in app.achievements else s for s in it.sources]
            cells = [it.setting, it.value, it.label, ", ".join(names)]
            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col == 2:
                    cell.setForeground(QBrush(QColor(LABEL_COLOURS[it.label])))
                elif col == 3:
                    cell.setForeground(QBrush(QColor(C["muted"])))
                elif it.label == "Free":
                    cell.setForeground(QBrush(QColor(C["faint"])))
                self.check.setItem(r, col, cell)
        self.check.resizeRowsToContents()

    def _copy(self) -> None:
        sel = self.app.selected_achs()
        if not sel:
            return
        lines = ["Targets:"] + [f"  - {a['name']}: {a['description']}" for a in sel] + ["", "Lobby:"]
        for it in batch.lobby_checklist(sel, self.app.leaders):
            lines.append(f"  [{it.label}] {it.setting}: {it.value}")
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.app.toast.emit("success", "Checklist copied to clipboard")

    # Suggestions ------------------------------------------------------------------------
    def _max_diff_changed(self, text: str) -> None:
        self.app.settings.max_difficulty = text.lower()
        self.app.save_settings()

    def generate(self) -> None:
        app = self.app
        if not app.pct:
            app.toast.emit("warning", "Sync Steam first so the planner knows rarity and what you've unlocked.")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            locked = app.locked
            best = planner.suggest(locked, app.leaders, app.pct, app.settings.max_difficulty, limit=10)
            plan = planner.season(locked, app.leaders, app.pct, app.settings.max_difficulty, games=8)
        finally:
            QApplication.restoreOverrideCursor()
        self.best.set_cards([SuggestionCard(app, s, i + 1, app.set_selected) for i, s in enumerate(best)] or
                            [EmptyState("Nothing found", "No compatible batch at this difficulty.")])
        self.season.set_cards([SuggestionCard(app, s, i + 1, app.set_selected) for i, s in enumerate(plan)] or
                              [EmptyState("Nothing found", "")])

    # Saved batches ----------------------------------------------------------------------
    def _reload_saved(self) -> None:
        self.saved = config.read_json(config.BATCHES, [])
        self.saved_combo.clear()
        self.saved_combo.addItem("Saved batches…")
        for b in self.saved:
            self.saved_combo.addItem(f"{b['name']} ({len(b['ids'])})")

    def _save(self) -> None:
        if not self.app.selected:
            self.app.toast.emit("warning", "Nothing to save: the batch is empty.")
            return
        name, ok = QInputDialog.getText(self, "Save batch", "Name:")
        if not ok or not name.strip():
            return
        self.saved = [b for b in self.saved if b["name"] != name.strip()]
        self.saved.append({"name": name.strip(), "ids": self.app.selected, "created": time.time()})
        config.write_json(config.BATCHES, self.saved)
        self._reload_saved()
        self.app.toast.emit("success", f"Saved '{name.strip()}'")

    def _load_saved(self, idx: int) -> None:
        if idx <= 0:
            return
        b = self.saved[idx - 1]
        self.app.set_selected([i for i in b["ids"] if i not in self.app.unlocked])
        self.saved_combo.setCurrentIndex(0)
        self.app.toast.emit("info", f"Loaded '{b['name']}'")
