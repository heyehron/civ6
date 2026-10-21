"""In-game page: live state source, next action, per-target progress with manual ticks, alerts."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QProgressBar, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ... import config
from ...dataset import DATA_DIR
from ...state import diagnose
from ...state.log_source import FileSource, LogSource
from ..appstate import AppState
from ..hud import Hud
from ..theme import C
from ..widgets import Card, PageHeader, button, clear_layout, label

DEMO = DATA_DIR / "demo" / "batch_a_turn40.json"


class InGamePage(QWidget):
    ask_ai = Signal(str)

    def __init__(self, app: AppState):
        super().__init__()
        self.app = app
        self.source = None
        self.hud: Hud | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.header = PageHeader("In game", "Reads the advisor mod's output from Lua.log. "
                                            "Open the HUD on your second monitor before launching Civ.")
        self.src_combo = QComboBox()
        self.src_combo.addItems(["Live: Lua.log", "Demo snapshot", "Snapshot file…"])
        self.header.actions.addWidget(self.src_combo)
        self.run_btn = button("Connect", "Primary", slot=self.toggle_source)
        self.header.actions.addWidget(self.run_btn)
        self.header.actions.addWidget(button("Open HUD", slot=self.open_hud))
        self.header.actions.addWidget(button("Check setup", slot=self.check_setup))
        lay.addWidget(self.header)
        self.status = label("Not connected", "Muted", wrap=True)
        lay.addWidget(self.status)

        self.diag = Card("Setup check")
        self.diag_body = QVBoxLayout()
        self.diag_body.setSpacing(6)
        self.diag.body.addLayout(self.diag_body)
        drow = QHBoxLayout()
        drow.addWidget(button("Install / update mod", "Primary", slot=self.install_mod))
        drow.addWidget(button("Re-check", slot=self.check_setup))
        drow.addWidget(button("Reset HUD position", "Ghost", slot=self.reset_hud))
        drow.addStretch(1)
        drow.addWidget(button("Hide", "Ghost", slot=self.diag.hide))
        self.diag.body.addLayout(drow)
        self.diag.hide()
        lay.addWidget(self.diag)

        hero = Card(name="Hero")
        hero.body.addWidget(label("NEXT ACTION", "SectionTitle"))
        self.next = label("Pick targets in the planner", "HeroText", wrap=True)
        hero.body.addWidget(self.next)
        self.next_detail = label("", "Muted", wrap=True)
        hero.body.addWidget(self.next_detail)
        hrow = QHBoxLayout()
        hrow.addStretch(1)
        hrow.addWidget(button("✦ Ask AI what to do now", slot=lambda: self.ask_ai.emit("What now?")))
        hero.body.addLayout(hrow)
        lay.addWidget(hero)

        split = QSplitter()
        tcard = Card("Targets — tick manual steps when done")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Step", "Progress", "Tracking"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        th = self.tree.header()
        th.setSectionResizeMode(0, QHeaderView.Stretch)
        th.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 140)
        th.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._item_changed)
        tcard.body.addWidget(self.tree, 1)
        split.addWidget(tcard)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)
        acard = Card("Alerts")
        self.alerts = QVBoxLayout()
        acard.body.addLayout(self.alerts)
        rv.addWidget(acard)
        scard = Card("Game state")
        self.state_lbl = label("", wrap=True)
        self.state_lbl.setTextFormat(Qt.RichText)
        self.state_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scard.body.addWidget(self.state_lbl)
        scard.body.addStretch(1)
        rv.addWidget(scard, 1)
        split.addWidget(right)
        split.setSizes([760, 440])
        lay.addWidget(split, 1)

        self._updating = False
        app.advice_changed.connect(self.refresh)
        app.game_state_changed.connect(self.refresh_state)
        self.refresh()
        self.refresh_state()

    # Sources ----------------------------------------------------------------------------
    def toggle_source(self) -> None:
        if self.source is not None:
            self.source.stop()
            self.source = None
            self.run_btn.setText("Connect")
            self.status.setText("Disconnected")
            return
        mode = self.src_combo.currentIndex()
        if mode == 0:
            self.source = LogSource(self.app.settings.lua_log, parent=self)
        else:
            path = str(DEMO)
            if mode == 2:
                path, _ = QFileDialog.getOpenFileName(self, "Snapshot JSON", str(Path.home()), "JSON (*.json)")
                if not path:
                    return
            self.source = FileSource(path, parent=self)
        self.source.state_changed.connect(self.app.set_game_state)
        self.source.status_changed.connect(self.status.setText)
        self.run_btn.setText("Disconnect")
        self.source.start(from_end=False)

    def open_hud(self) -> None:
        if self.hud is None:
            self.hud = Hud(self.app)
            self.hud.place()
        self.hud.show()
        self.hud.raise_()

    def reset_hud(self) -> None:
        if self.hud is None:
            self.hud = Hud(self.app)
        self.hud.place(reset=True)
        self.hud.show()
        self.hud.raise_()

    def check_setup(self) -> None:
        clear_layout(self.diag_body)
        colours = {"ok": C["green"], "warn": C["amber"], "fail": C["red"], "info": C["muted"]}
        marks = {"ok": "✓", "warn": "⚠", "fail": "✖", "info": "•"}
        for c in diagnose.run(self.app.settings.lua_log):
            text = f"{marks[c.level]} {c.text}" + (f"<br><span style='color:{C['faint']}'>→ {c.fix}</span>" if c.fix else "")
            lab = label(text, wrap=True)
            lab.setTextFormat(Qt.RichText)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setStyleSheet(f"color: {colours[c.level]}; background: transparent;")
            self.diag_body.addWidget(lab)
        self.diag.show()

    def install_mod(self) -> None:
        civ = config.find_civ_dir()
        if civ is None:
            self.app.toast.emit("error", "Civ VI's user folder was not found. Start Civ VI once, then try again.")
            return
        try:
            dest = diagnose.install_mod(civ)
        except OSError as exc:
            self.app.toast.emit("error", f"Could not install the mod: {exc}")
            return
        self.app.toast.emit("success", f"Mod installed to {dest}. Enable it under Additional Content, then start a game.")
        self.check_setup()

    # Rendering --------------------------------------------------------------------------
    def refresh(self) -> None:
        app = self.app
        adv = app.advice
        if adv and adv.next_action:
            ps, step = adv.next_action
            self.next.setText(step.step["text"])
            dl = f" · by turn {step.step['deadline_turn']}" if step.step.get("deadline_turn") else ""
            self.next_detail.setText(f"{ps.title}{dl}. {step.step.get('detail', '')}")
        else:
            self.next.setText("All tracked steps complete" if adv else "Pick targets in the planner")
            self.next_detail.setText("")

        self._updating = True
        expanded = {self.tree.topLevelItem(i).data(0, Qt.UserRole)
                    for i in range(self.tree.topLevelItemCount()) if self.tree.topLevelItem(i).isExpanded()}
        self.tree.clear()
        for ps in (adv.statuses if adv else []):
            top = QTreeWidgetItem([ps.title, "", ""])
            top.setData(0, Qt.UserRole, ps.achievement)
            colour = C["green"] if ps.done else C["red"] if ps.failed else C["text"]
            top.setForeground(0, QBrush(QColor(colour)))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(round(ps.progress * 100))
            bar.setFixedSize(120, 10)
            self.tree.setItemWidget(top, 1, bar)
            top.setText(2, f"{round(ps.progress * 100)}%")
            for s in ps.steps:
                key = f"{ps.achievement}:{s.step['id']}"
                child = QTreeWidgetItem([s.step["text"], "", ""])
                child.setData(0, Qt.UserRole, key)
                manual = s.step.get("manual") or not s.trackable
                tip = s.step.get("detail", "")
                if s.step.get("deadline_turn"):
                    tip += f"\nDeadline: turn {s.step['deadline_turn']}"
                child.setToolTip(0, tip.strip())
                if manual:
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.Checked if s.done else Qt.Unchecked)
                    child.setText(2, "manual" if s.step.get("manual") else "no data yet")
                else:
                    child.setText(2, "auto")
                state = "done" if s.done else "failed" if s.failed else "missed" if s.missed else \
                    "at risk" if s.at_risk else ""
                child.setText(1, state)
                col = {"done": C["green"], "failed": C["red"], "missed": C["red"], "at risk": C["amber"]}.get(state)
                if col:
                    child.setForeground(1, QBrush(QColor(col)))
                if s.done:
                    child.setForeground(0, QBrush(QColor(C["muted"])))
                top.addChild(child)
            top.setExpanded(ps.achievement in expanded or not expanded)
        self._updating = False

        while self.alerts.count():
            it = self.alerts.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        alerts = adv.alerts if adv else []
        if not alerts:
            self.alerts.addWidget(label("No alerts.", "Faint"))
        for al in alerts[:8]:
            colour = C["red"] if al.level in ("failed", "missed") else C["amber"]
            lab = label(("✖ " if al.level in ("failed", "missed") else "⚠ ") + al.text, wrap=True)
            lab.setStyleSheet(f"color: {colour}; background: transparent;")
            self.alerts.addWidget(lab)

    def _item_changed(self, item: QTreeWidgetItem, col: int) -> None:
        if self._updating or col != 0 or not (item.flags() & Qt.ItemIsUserCheckable):
            return
        self.app.set_manual(item.data(0, Qt.UserRole), item.checkState(0) == Qt.Checked)

    def refresh_state(self) -> None:
        st = self.app.game_state
        if st is None:
            self.state_lbl.setText(f"<span style='color:{C['faint']}'>No game data yet.</span>")
            return
        leader = self.app.leaders.get(st.leader or "", {}).get("name", st.leader or "?")
        rel = st.religion.get("name") or st.religion.get("type") or "none"
        f = st.fields()
        rows = [
            ("Turn", f"{st.turn} · {(st.era or '?').title()} era"),
            ("Leader", leader),
            ("Difficulty", (st.difficulty or "?").title()),
            ("Map", f"{(st.map_type or '?').replace('_', ' ').title()} · {(st.map_size or '?').title()}"),
            ("Speed", (st.speed or "?").title()),
            ("Modes", ", ".join(m.replace('_', ' ') for m in st.game_modes) or "none"),
            ("Cities", f"{f['cities_count']} · pop {f['total_population']}"),
            ("Age", f"{(st.age or '?').title()} · era score {st.era_score if st.era_score is not None else '?'}"),
            ("Religion", rel),
            ("Suzerain of", ", ".join(f["suzerain_of"]) or "none"),
            ("Yields", " · ".join(f"{k} {v:g}" for k, v in st.yields.items()) or "?"),
        ]
        self.state_lbl.setText("<table cellspacing=4>" + "".join(
            f"<tr><td style='color:{C['muted']};padding-right:12px'>{k}</td><td>{v}</td></tr>" for k, v in rows)
            + "</table>")
