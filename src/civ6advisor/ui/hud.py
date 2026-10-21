"""Read-only HUD (SPEC §4.7). A normal window with a title bar, so it can be dragged and resized
anywhere. It stays on top, remembers its position and size, and has no controls that need clicking
during play."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .appstate import AppState
from .theme import C


class Hud(QWidget):
    def __init__(self, app: AppState):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.app = app
        self.setWindowTitle("Civ VI Advisor HUD  ·  drag the title bar to move, drag edges to resize")
        self.setMinimumSize(320, 360)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_geometry)
        self.setStyleSheet(f"""
            QWidget#HudRoot {{ background: {C['bg']}; border: none; }}
            QLabel {{ background: transparent; color: {C['text']}; }}
            QLabel#HudTurn {{ color: {C['muted']}; font-size: 15px; }}
            QLabel#HudKicker {{ color: {C['gold']}; font-size: 13px; font-weight: 700; letter-spacing: 2px; }}
            QLabel#HudNext {{ color: {C['gold_hi']}; font-size: 30px; font-weight: 800; }}
            QLabel#HudDetail {{ color: {C['muted']}; font-size: 16px; }}
            QLabel#HudTarget {{ font-size: 16px; }}
            QLabel#HudAlert {{ font-size: 16px; font-weight: 600; }}
            QProgressBar {{ background: {C['panel']}; border: none; border-radius: 4px; max-height: 8px; }}
            QProgressBar::chunk {{ background: {C['gold']}; border-radius: 4px; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("HudRoot")
        outer.addWidget(root)
        self.lay = QVBoxLayout(root)
        self.lay.setContentsMargins(28, 24, 28, 24)
        self.lay.setSpacing(14)
        self.turn = QLabel()
        self.turn.setObjectName("HudTurn")
        self.lay.addWidget(self.turn)
        k = QLabel("NEXT ACTION")
        k.setObjectName("HudKicker")
        self.lay.addWidget(k)
        self.next = QLabel()
        self.next.setObjectName("HudNext")
        self.next.setWordWrap(True)
        self.lay.addWidget(self.next)
        self.detail = QLabel()
        self.detail.setObjectName("HudDetail")
        self.detail.setWordWrap(True)
        self.lay.addWidget(self.detail)
        self.alerts = QVBoxLayout()
        self.lay.addLayout(self.alerts)
        k2 = QLabel("TARGETS")
        k2.setObjectName("HudKicker")
        self.lay.addWidget(k2)
        self.targets = QVBoxLayout()
        self.targets.setSpacing(10)
        self.lay.addLayout(self.targets)
        self.lay.addStretch(1)
        app.advice_changed.connect(self.refresh)
        app.game_state_changed.connect(self.refresh)
        app.settings_changed.connect(self._apply_settings)
        self._apply_settings()
        self.refresh()

    def _apply_settings(self) -> None:
        self.setWindowOpacity(self.app.settings.hud_opacity)

    def default_geometry(self) -> QRect:
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        idx = self.app.settings.hud_screen
        if 0 <= idx < len(screens):
            screen = screens[idx]
        else:
            others = [s for s in screens if s is not primary]
            screen = others[0] if others else primary
        geo = screen.availableGeometry()
        w = min(560, max(360, geo.width() // 3))
        h = min(geo.height() - 80, 820)
        return QRect(geo.right() - w - 20, geo.top() + 40, w, h)

    def place(self, reset: bool = False) -> None:
        """Restore the last position if it is still on a connected screen, else use the default."""
        saved = self.app.settings.hud_geometry
        rect = QRect(*saved) if len(saved) == 4 and not reset else None
        if rect is not None and not any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens()):
            rect = None
        self.setGeometry(rect or self.default_geometry())

    def _save_geometry(self) -> None:
        g = self.geometry()
        self.app.settings.hud_geometry = [g.x(), g.y(), g.width(), g.height()]
        self.app.settings.save()

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        self._save_timer.start(500)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._save_timer.start(500)

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                Hud._clear(it.layout())

    def refresh(self) -> None:
        app = self.app
        st = app.game_state
        self.turn.setText(f"Turn {st.turn} · {(st.era or '').title()} era" if st else "Waiting for game data…")
        adv = app.advice
        if adv and adv.next_action:
            ps, step = adv.next_action
            self.next.setText(step.step["text"])
            dl = f"  ·  by turn {step.step['deadline_turn']}" if step.step.get("deadline_turn") else ""
            self.detail.setText(f"{ps.title}{dl}\n{step.step.get('detail', '')}".strip())
        else:
            self.next.setText("All steps complete" if adv else "Pick targets in the planner")
            self.detail.setText("")
        self._clear(self.alerts)
        if adv:
            colours = {"failed": C["red"], "missed": C["red"], "at_risk": C["amber"]}
            for al in adv.alerts[:4]:
                lab = QLabel(("✖ " if al.level in ("failed", "missed") else "⚠ ") + al.text)
                lab.setObjectName("HudAlert")
                lab.setWordWrap(True)
                lab.setStyleSheet(f"color: {colours.get(al.level, C['amber'])};")
                self.alerts.addWidget(lab)
        self._clear(self.targets)
        for ps in (adv.statuses if adv else []):
            row = QHBoxLayout()
            name = QLabel(("✓ " if ps.done else "✖ " if ps.failed else "") + ps.title)
            name.setObjectName("HudTarget")
            colour = C["green"] if ps.done else C["red"] if ps.failed else C["text"]
            name.setStyleSheet(f"color: {colour};")
            row.addWidget(name, 1)
            pct = QLabel(f"{round(ps.progress * 100)}%")
            pct.setStyleSheet(f"color: {C['muted']}; font-size: 15px;")
            row.addWidget(pct)
            self.targets.addLayout(row)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(round(ps.progress * 100))
            bar.setTextVisible(False)
            self.targets.addWidget(bar)
