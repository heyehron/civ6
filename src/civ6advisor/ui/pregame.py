"""Pre-game window (SPEC §4.7): sync, achievement picker, conflict greying, lobby checklist."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..engine import batch
from ..steam import sync as steam

COLS = ["", "Achievement", "Global %", "Score", "Content", "Verified", "Description"]
LABEL_COLOURS = {"Required": "#c0392b", "Recommended": "#2e86c1", "Free": "#7f8c8d"}


class _SyncWorker(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, profile: str):
        super().__init__()
        self.profile = profile

    def run(self) -> None:
        try:
            self.done.emit(steam.sync(self.profile))
        except steam.SteamError as exc:
            self.failed.emit(str(exc))


class _NumItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        return (a if a is not None else -1e9) < (b if b is not None else -1e9)


class PreGameWindow(QMainWindow):
    def __init__(self, achievements: dict[str, dict], leaders: dict[str, dict]):
        super().__init__()
        self.setWindowTitle("Civ VI Achievement Advisor")
        self.resize(1500, 850)
        self.ach, self.leaders = achievements, leaders
        self.selected: list[str] = []
        self.unlocked: set[str] = set()
        self.pct: dict[str, float] = {}
        self._thread: QThread | None = None

        cfg = steam.load_config()
        self.profile = QLineEdit(cfg.get("profile", ""))
        self.profile.setPlaceholderText("Steam custom URL name or SteamID64")
        self.sync_btn = QPushButton("Sync Steam")
        self.sync_btn.clicked.connect(self.start_sync)
        self.status = QLabel("Not synced")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or description")
        self.show_unlocked = QCheckBox("Show unlocked")
        self.show_scenarios = QCheckBox("Show scenarios")
        self.show_scenarios.setChecked(True)
        self.hide_conflicts = QCheckBox("Hide conflicting")
        for w in (self.search,):
            w.textChanged.connect(self.refresh)
        for w in (self.show_unlocked, self.show_scenarios, self.hide_conflicts):
            w.toggled.connect(self.refresh)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(len(COLS) - 1, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)

        self.sel_list = QListWidget()
        self.sel_list.itemDoubleClicked.connect(self._unselect)
        self.clear_btn = QPushButton("Clear selection")
        self.clear_btn.clicked.connect(self._clear)
        self.check = QTableWidget(0, 4)
        self.check.setHorizontalHeaderLabels(["Setting", "Value", "Label", "Because of"])
        self.check.verticalHeader().setVisible(False)
        self.check.setEditTriggers(QTableWidget.NoEditTriggers)
        ch = self.check.horizontalHeader()
        ch.setSectionResizeMode(QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(3, QHeaderView.Stretch)

        top = QHBoxLayout()
        for w in (QLabel("Profile:"), self.profile, self.sync_btn, self.status):
            top.addWidget(w)
        filt = QHBoxLayout()
        for w in (self.search, self.show_unlocked, self.show_scenarios, self.hide_conflicts):
            filt.addWidget(w)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addLayout(filt)
        lv.addWidget(self.table)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("Targets (double-click to remove)"))
        rv.addWidget(self.sel_list, 1)
        rv.addWidget(self.clear_btn)
        rv.addWidget(QLabel("Lobby checklist"))
        rv.addWidget(self.check, 3)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([950, 550])
        root = QWidget()
        v = QVBoxLayout(root)
        v.addLayout(top)
        v.addWidget(split, 1)
        self.setCentralWidget(root)

        cached = steam.load_cache()
        if cached:
            self._apply_sync(cached)
        else:
            self.refresh()

    # Steam -------------------------------------------------------------------------------
    def start_sync(self) -> None:
        profile = self.profile.text().strip()
        if not profile:
            self.status.setText("Enter a profile first")
            return
        cfg = steam.load_config()
        cfg["profile"] = profile
        steam.save_config(cfg)
        self.sync_btn.setEnabled(False)
        self.status.setText("Syncing…")
        self._thread = QThread(self)
        self._worker = _SyncWorker(profile)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._apply_sync)
        self._worker.failed.connect(self._sync_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _apply_sync(self, res: steam.SyncResult) -> None:
        self.sync_btn.setEnabled(True)
        self.unlocked, self.pct = res.unlocked, res.pct
        when = dt.datetime.fromtimestamp(res.synced_at).strftime("%Y-%m-%d %H:%M")
        src = "cache" if res.from_cache else "Steam"
        self.status.setText(f"{len(res.unlocked)}/{len(self.ach)} unlocked · last synced {when} ({src})")
        self.selected = [s for s in self.selected if s not in self.unlocked]
        self.refresh()

    def _sync_failed(self, msg: str) -> None:
        self.sync_btn.setEnabled(True)
        self.status.setText(f"Sync failed: {msg}")

    # Selection ---------------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0 or self._refreshing:
            return
        aid = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked and aid not in self.selected:
            self.selected.append(aid)
        elif item.checkState() == Qt.Unchecked and aid in self.selected:
            self.selected.remove(aid)
        self.refresh()

    def _unselect(self, item) -> None:
        aid = item.data(Qt.UserRole)
        if aid in self.selected:
            self.selected.remove(aid)
        self.refresh()

    def _clear(self) -> None:
        self.selected.clear()
        self.refresh()

    # Rendering ---------------------------------------------------------------------------
    _refreshing = False

    def refresh(self) -> None:
        self._refreshing = True
        sel = [self.ach[s] for s in self.selected]
        needle = self.search.text().lower()
        rows = []
        for aid, a in self.ach.items():
            is_sel = aid in self.selected
            if aid in self.unlocked and not self.show_unlocked.isChecked() and not is_sel:
                continue
            if a["constraints"].get("scenario") and not self.show_scenarios.isChecked() and not is_sel:
                continue
            if needle and needle not in a["name"].lower() and needle not in a["description"].lower():
                continue
            conflicts = [] if is_sel else batch.conflicts_with(sel, a, self.leaders)
            if conflicts and self.hide_conflicts.isChecked():
                continue
            pct = self.pct.get(aid)
            sc = None if is_sel or conflicts else batch.score(a, sel, pct, self.leaders)
            rows.append((a, is_sel, conflicts, pct, sc))

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        grey = QBrush(QColor("#9a9a9a"))
        for r, (a, is_sel, conflicts, pct, sc) in enumerate(rows):
            box = QTableWidgetItem()
            box.setData(Qt.UserRole, a["id"])
            flags = Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
            box.setFlags(flags if not conflicts else Qt.NoItemFlags)
            box.setCheckState(Qt.Checked if is_sel else Qt.Unchecked)
            name = QTableWidgetItem(a["name"] + ("  ✓" if a["id"] in self.unlocked else ""))
            pct_item = _NumItem("" if pct is None else f"{pct:.1f}")
            pct_item.setData(Qt.UserRole, pct)
            score_item = _NumItem("" if sc is None else f"{sc:.2f}")
            score_item.setData(Qt.UserRole, sc if sc is not None else (1e9 if is_sel else None))
            verified = QTableWidgetItem("yes" if a.get("verified") else "⚠ draft")
            if not a.get("verified"):
                inf = ", ".join(a.get("inferred") or []) or "none"
                verified.setToolTip(f"Constraints not verified. Inferred fields: {inf}. {a.get('notes', '')}")
            cells = [box, name, pct_item, score_item, QTableWidgetItem(a["content"]), verified,
                     QTableWidgetItem(a["description"])]
            tip = "\n".join(f"Conflicts on {c.attribute}: {c.detail} (with "
                            f"{', '.join(self.ach[i]['name'] for i in c.ids if i != a['id']) or 'itself'})"
                            for c in conflicts)
            for col, it in enumerate(cells):
                if conflicts:
                    it.setForeground(grey)
                    it.setToolTip(tip)
                self.table.setItem(r, col, it)
        self.table.setSortingEnabled(True)
        self.table.sortItems(3 if sel else 2, Qt.DescendingOrder if sel else Qt.AscendingOrder)

        self.sel_list.clear()
        for a in sel:
            self.sel_list.addItem(a["name"])
            self.sel_list.item(self.sel_list.count() - 1).setData(Qt.UserRole, a["id"])

        items = batch.lobby_checklist(sel, self.leaders) if sel else []
        self.check.setRowCount(len(items))
        for r, it in enumerate(items):
            names = [self.ach[s]["name"] if s in self.ach else s for s in it.sources]
            cells = [it.setting, it.value, it.label, ", ".join(names)]
            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col == 2:
                    cell.setForeground(QBrush(QColor(LABEL_COLOURS[it.label])))
                self.check.setItem(r, col, cell)
        self._refreshing = False
