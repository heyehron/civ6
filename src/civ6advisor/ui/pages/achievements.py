"""Achievements page: browse, filter, pick targets, inspect and edit constraints."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QScrollArea, QSpinBox, QSplitter, QTableView, QVBoxLayout, QWidget,
)

from ...engine import batch
from ..appstate import AppState
from ..summaries import constraint_rows, short_tags
from ..theme import C, CONTENT_COLOURS, rarity_colour
from ..widgets import Badge, Card, FlowLayout, IconCache, PageHeader, button, clear_layout, label, placeholder_icon

COLS = ["", "Achievement", "Global %", "Fit score", "Pack", "Requirements", "Data"]
PACK_LABELS = {"base": "Base", "rise_and_fall": "Rise & Fall", "gathering_storm": "Gathering Storm",
               "new_frontier": "New Frontier", "leader_pack": "Civ packs", "scenario": "Scenarios"}


class AchievementModel(QAbstractTableModel):
    def __init__(self, app: AppState, icons: IconCache):
        super().__init__()
        self.app, self.icons = app, icons
        self.ids: list[str] = []
        self.conflicts: dict[str, list[batch.Conflict]] = {}
        self.scores: dict[str, float] = {}
        self.tags: dict[str, str] = {}
        icons.loaded.connect(self._icon_loaded)
        self.rebuild()

    def rebuild(self) -> None:
        self.beginResetModel()
        app = self.app
        self.ids = list(app.achievements)
        sel = app.selected_achs()
        w = app.weights()
        self.conflicts, self.scores = {}, {}
        for aid, a in app.achievements.items():
            if aid in app.selected:
                continue
            self.tags[aid] = short_tags(a, app.leaders)
            cf = batch.conflicts_with(sel, a, app.leaders)
            if cf:
                self.conflicts[aid] = cf
            else:
                self.scores[aid] = batch.score(a, sel, app.pct.get(aid), app.leaders, w)
        for aid in app.selected:
            self.tags[aid] = short_tags(app.achievements[aid], app.leaders)
        self.endResetModel()

    def _icon_loaded(self, aid: str) -> None:
        if aid in self.ids:
            r = self.ids.index(aid)
            self.dataChanged.emit(self.index(r, 1), self.index(r, 1), [Qt.DecorationRole])

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ids)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[section]
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        aid = self.ids[index.row()]
        a = self.app.achievements[aid]
        col = index.column()
        pct = self.app.pct.get(aid)
        unlocked = aid in self.app.unlocked
        conflicted = aid in self.conflicts
        if role == Qt.UserRole:
            return aid
        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if aid in self.app.selected else Qt.Unchecked
        if role == Qt.DisplayRole:
            if col == 1:
                return a["name"]
            if col == 2:
                return "" if pct is None else f"{pct:.1f}%"
            if col == 3:
                return "" if aid not in self.scores or unlocked else f"{self.scores[aid]:.1f}"
            if col == 4:
                return PACK_LABELS.get(a["content"], a["content"])
            if col == 5:
                return self.tags.get(aid, "")
            if col == 6:
                return "verified" if a.get("verified") else "draft"
        if role == Qt.DecorationRole and col == 1:
            pm = self.icons.get(aid, a.get("icon"))
            pm = pm or placeholder_icon(32, a["name"])
            return pm.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if role == Qt.ForegroundRole:
            if conflicted and not unlocked:
                return QBrush(QColor(C["faint"]))
            if unlocked:
                return QBrush(QColor(C["green"])) if col == 1 else QBrush(QColor(C["faint"]))
            if col == 2:
                return QBrush(QColor(rarity_colour(pct)))
            if col == 4:
                return QBrush(QColor(CONTENT_COLOURS.get(a["content"], C["muted"])))
            if col == 6:
                return QBrush(QColor(C["green"] if a.get("verified") else C["amber"]))
            if col in (3, 5):
                return QBrush(QColor(C["muted"]))
        if role == Qt.FontRole and col == 1 and aid in self.app.selected:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ToolTipRole:
            if conflicted:
                return "Conflicts with your targets:\n" + "\n".join(
                    f"• {c.detail} ({', '.join(self.app.achievements[i]['name'] for i in c.ids if i != aid) or 'out of scope'})"
                    for c in self.conflicts[aid])
            return a["description"]
        if role == Qt.UserRole + 1:  # sort key
            if col == 2:
                return pct if pct is not None else 999.0
            if col == 3:
                return self.scores.get(aid, -999.0) if aid not in self.app.selected else 999.0
            if col == 0:
                return 1 if aid in self.app.selected else 0
            return self.data(index, Qt.DisplayRole)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            aid = self.ids[index.row()]
            conflicts = self.app.toggle(aid)
            if conflicts:
                self.app.toast.emit("warning", f"Can't add: {conflicts[0].detail}")
            return True
        return False


class Filter(QSortFilterProxyModel):
    def __init__(self, app: AppState):
        super().__init__()
        self.app = app
        self.text = ""
        self.status = "locked"
        self.packs: set[str] = set()
        self.compatible_only = False
        self.hide_scenarios = False
        self.setSortRole(Qt.UserRole + 1)

    def filterAcceptsRow(self, row, parent) -> bool:
        m: AchievementModel = self.sourceModel()
        aid = m.ids[row]
        a = self.app.achievements[aid]
        selected = aid in self.app.selected
        if selected:
            return True
        unlocked = aid in self.app.unlocked
        if self.status == "locked" and unlocked:
            return False
        if self.status == "unlocked" and not unlocked:
            return False
        if self.packs and a["content"] not in self.packs:
            return False
        if self.hide_scenarios and a["constraints"].get("scenario"):
            return False
        if self.compatible_only and aid in m.conflicts:
            return False
        if self.text:
            hay = f"{a['name']} {a['description']} {m.tags.get(aid, '')}".lower()
            return all(t in hay for t in self.text.lower().split())
        return True


class DetailPanel(QScrollArea):
    open_playbook = Signal(str)
    ask_ai = Signal(str)

    def __init__(self, app: AppState, icons: IconCache):
        super().__init__()
        self.app, self.icons = app, icons
        self.aid: str | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(380)
        host = QWidget()
        self.setWidget(host)
        self.lay = QVBoxLayout(host)
        self.lay.setContentsMargins(4, 0, 4, 0)
        self.lay.setSpacing(12)

        head = Card()
        row = QHBoxLayout()
        self.icon = QLabel()
        self.icon.setFixedSize(64, 64)
        row.addWidget(self.icon)
        col = QVBoxLayout()
        self.name = label("", "Big", wrap=True)
        col.addWidget(self.name)
        self.badges = FlowLayout()
        col.addLayout(self.badges)
        row.addLayout(col, 1)
        head.body.addLayout(row)
        self.desc = label("", wrap=True)
        self.desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.body.addWidget(self.desc)
        actions = QHBoxLayout()
        self.toggle_btn = button("Add to batch", "Primary", slot=self._toggle)
        actions.addWidget(self.toggle_btn)
        actions.addWidget(button("Playbook", slot=lambda: self.aid and self.open_playbook.emit(self.aid)))
        actions.addWidget(button("Ask AI", slot=lambda: self.aid and self.ask_ai.emit(self.aid)))
        actions.addStretch(1)
        head.body.addLayout(actions)
        self.lay.addWidget(head)

        self.conflict_card = Card("Conflicts with your batch")
        self.conflict_text = label("", wrap=True)
        self.conflict_text.setStyleSheet(f"color: {C['red']}; background: transparent;")
        self.conflict_card.body.addWidget(self.conflict_text)
        self.lay.addWidget(self.conflict_card)

        self.cons_card = Card("Requirements")
        self.cons_grid = QGridLayout()
        self.cons_grid.setHorizontalSpacing(12)
        self.cons_grid.setVerticalSpacing(6)
        self.cons_card.body.addLayout(self.cons_grid)
        self.lay.addWidget(self.cons_card)

        edit = Card("Your notes")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.effort = QSpinBox()
        self.effort.setRange(0, 5)
        self.effort.setSpecialValueText("unset")
        self.risk = QSpinBox()
        self.risk.setRange(0, 5)
        self.risk.setSpecialValueText("unset")
        self.verified = QCheckBox("Constraints checked by me")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(90)
        form.addRow("Effort (1–5)", self.effort)
        form.addRow("Risk (1–5)", self.risk)
        form.addRow("", self.verified)
        edit.body.addLayout(form)
        edit.body.addWidget(self.notes)
        save = button("Save", slot=self._save)
        edit.body.addWidget(save, 0, Qt.AlignRight)
        self.lay.addWidget(edit)
        self.lay.addStretch(1)
        self.show_achievement(None)

    def show_achievement(self, aid: str | None) -> None:
        self.aid = aid
        visible = aid is not None
        for i in range(self.lay.count()):
            w = self.lay.itemAt(i).widget()
            if w:
                w.setVisible(visible)
        if not visible:
            return
        app = self.app
        a = app.achievements[aid]
        pm = self.icons.get(aid, a.get("icon")) or placeholder_icon(64, a["name"])
        self.icon.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.name.setText(a["name"])
        self.desc.setText(a["description"])
        clear_layout(self.badges)
        pct = app.pct.get(aid)
        if pct is not None:
            self.badges.addWidget(Badge(f"{pct:.1f}% of players", rarity_colour(pct)))
        self.badges.addWidget(Badge(PACK_LABELS.get(a["content"], a["content"]),
                                    CONTENT_COLOURS.get(a["content"], C["muted"])))
        if aid in app.unlocked:
            self.badges.addWidget(Badge("Unlocked", C["green"], filled=True))
        self.badges.addWidget(Badge("verified" if a.get("verified") else "draft",
                                    C["green"] if a.get("verified") else C["amber"]))
        if aid in app.playbooks:
            self.badges.addWidget(Badge("playbook", C["blue"]))

        sel = aid in app.selected
        self.toggle_btn.setText("Remove from batch" if sel else "Add to batch")
        self.toggle_btn.setObjectName("" if sel else "Primary")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)
        conflicts = [] if sel else batch.conflicts_with(app.selected_achs(), a, app.leaders)
        self.toggle_btn.setEnabled(sel or not conflicts)
        self.conflict_card.setVisible(bool(conflicts))
        self.conflict_text.setText("\n".join(
            f"• {c.detail} — {', '.join(app.achievements[i]['name'] for i in c.ids if i != aid) or 'out of scope'}"
            for c in conflicts))

        while self.cons_grid.count():
            it = self.cons_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        rows = constraint_rows(a, app.leaders) or [("None", "Can be done in any game", False)]
        for r, (lab, val, inferred) in enumerate(rows):
            self.cons_grid.addWidget(label(lab, "Muted"), r, 0, Qt.AlignTop)
            v = label(val, wrap=True)
            self.cons_grid.addWidget(v, r, 1)
            self.cons_grid.addWidget(Badge("inferred" if inferred else "read", C["amber"] if inferred else C["faint"]),
                                     r, 2, Qt.AlignTop)
        self.cons_grid.setColumnStretch(1, 1)

        self.effort.setValue(a.get("effort") or 0)
        self.risk.setValue(a.get("risk") or 0)
        self.verified.setChecked(bool(a.get("verified")))
        self.notes.setPlainText(a.get("notes") or "")

    def _toggle(self) -> None:
        if self.aid:
            cf = self.app.toggle(self.aid)
            if cf:
                self.app.toast.emit("warning", f"Can't add: {cf[0].detail}")

    def _save(self) -> None:
        if not self.aid:
            return
        self.app.update_achievement(self.aid, effort=self.effort.value() or None, risk=self.risk.value() or None,
                                    verified=self.verified.isChecked(), notes=self.notes.toPlainText().strip())
        self.app.toast.emit("success", "Saved to data/achievements.json")


class AchievementsPage(QWidget):
    open_playbook = Signal(str)
    ask_ai = Signal(str)

    def __init__(self, app: AppState, icons: IconCache):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.header = PageHeader("Achievements", "")
        lay.addWidget(self.header)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, description or requirement (e.g. 'duel religious')")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        self.status_chips = {}
        for key, text in (("locked", "Locked"), ("unlocked", "Unlocked"), ("all", "All")):
            b = button(text, "Chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._set_status(k))
            self.status_chips[key] = b
            bar.addWidget(b)
        self.status_chips["locked"].setChecked(True)
        self.compat = button("Compatible only", "Chip")
        self.compat.setCheckable(True)
        bar.addWidget(self.compat)
        lay.addLayout(bar)

        packs = QHBoxLayout()
        packs.setSpacing(6)
        self.pack_chips = {}
        for key, text in PACK_LABELS.items():
            b = button(text.replace("&", "&&"), "Chip")
            b.setCheckable(True)
            b.toggled.connect(self._packs_changed)
            self.pack_chips[key] = b
            packs.addWidget(b)
        packs.addStretch(1)
        self.count = label("", "Faint")
        packs.addWidget(self.count)
        lay.addLayout(packs)

        self.model = AchievementModel(app, icons)
        self.proxy = Filter(app)
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(40)
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        h = self.view.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        for col, w in ((0, 34), (1, 300), (2, 80), (3, 80), (4, 120), (6, 70)):
            self.view.setColumnWidth(col, w)
        self.view.sortByColumn(2, Qt.AscendingOrder)
        self.view.selectionModel().currentRowChanged.connect(self._row_changed)

        self.detail = DetailPanel(app, icons)
        self.detail.open_playbook.connect(self.open_playbook)
        self.detail.ask_ai.connect(self.ask_ai)
        split = QSplitter()
        split.addWidget(self.view)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 400])
        lay.addWidget(split, 1)

        self.search.textChanged.connect(self._text_changed)
        self.compat.toggled.connect(self._compat_changed)
        app.selection_changed.connect(self.refresh)
        app.sync_changed.connect(self.refresh)
        app.dataset_changed.connect(self.refresh)
        app.playbooks_changed.connect(lambda: self.detail.show_achievement(self.detail.aid))
        app.settings_changed.connect(self.refresh)
        self.refresh()

    def _set_status(self, key: str) -> None:
        for k, b in self.status_chips.items():
            b.setChecked(k == key)
        self.proxy.status = key
        self._apply()

    def _packs_changed(self) -> None:
        self.proxy.packs = {k for k, b in self.pack_chips.items() if b.isChecked()}
        self._apply()

    def _text_changed(self, t: str) -> None:
        self.proxy.text = t.strip()
        self._apply()

    def _compat_changed(self, on: bool) -> None:
        self.proxy.compatible_only = on
        self._apply()

    def _apply(self) -> None:
        self.proxy.invalidateFilter()
        self.count.setText(f"{self.proxy.rowCount()} shown")

    def refresh(self) -> None:
        current = self.detail.aid
        self.model.rebuild()
        if self.app.selected:
            self.view.sortByColumn(3, Qt.DescendingOrder)
        self._apply()
        n_sel = len(self.app.selected)
        locked = len(self.app.locked)
        self.header.sub.setText(f"{locked} locked of {len(self.app.achievements)} · {n_sel} in your batch · "
                                "tick to add; greyed rows conflict with your batch (hover for why)")
        self.detail.show_achievement(current)
        if current:
            self.select(current, scroll=False)

    def select(self, aid: str, scroll: bool = True) -> None:
        if aid not in self.model.ids:
            return
        src = self.model.index(self.model.ids.index(aid), 1)
        idx = self.proxy.mapFromSource(src)
        if not idx.isValid():
            self._set_status("all")
            self.search.clear()
            idx = self.proxy.mapFromSource(src)
        if idx.isValid():
            flags = QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            self.view.selectionModel().setCurrentIndex(idx, flags)
            if scroll:
                self.view.scrollTo(idx, QAbstractItemView.PositionAtCenter)
        self.detail.show_achievement(aid)

    def _row_changed(self, cur, _prev) -> None:
        if cur.isValid():
            self.detail.show_achievement(self.proxy.data(cur, Qt.UserRole))
