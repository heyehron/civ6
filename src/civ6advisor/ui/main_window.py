"""Main window: sidebar navigation over the pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ..ai.prompts import QUICK_PROMPTS
from .appstate import AppState
from .pages.achievements import AchievementsPage
from .pages.assistant import AssistantPage
from .pages.ingame import InGamePage
from .pages.planner import PlannerPage
from .pages.playbooks import PlaybooksPage
from .pages.settings import SettingsPage, SteamSync
from .widgets import IconCache, Toast, button, label

NAV = [("achievements", "◈  Achievements"), ("planner", "▤  Batch planner"), ("playbooks", "☰  Playbooks"),
       ("ingame", "▶  In game"), ("assistant", "✦  Assistant"), ("settings", "⚙  Settings")]


class MainWindow(QMainWindow):
    def __init__(self, app: AppState):
        super().__init__()
        self.app = app
        self.setWindowTitle("Civ VI Achievement Advisor")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.icons = IconCache(self)
        self.syncer = SteamSync(app, self)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(2)
        sv.addWidget(label("CIV VI ADVISOR", "Brand"))
        sv.addWidget(label("Achievement hunting, planned", "BrandSub"))
        self.group = QButtonGroup(self)
        self.nav: dict[str, object] = {}
        for i, (key, text) in enumerate(NAV):
            b = button(text, "NavButton")
            b.setCheckable(True)
            b.setShortcut(f"Ctrl+{i + 1}")
            b.setToolTip(f"Ctrl+{i + 1}")
            self.group.addButton(b, i)
            self.nav[key] = b
            sv.addWidget(b)
        sv.addStretch(1)
        self.sync_btn = button("⟳  Sync Steam", "Ghost", slot=self.syncer.start)
        self.sync_btn.setStyleSheet("text-align: left; padding: 8px 16px;")
        sv.addWidget(self.sync_btn)
        self.footer = label("", "SidebarFooter", wrap=True)
        sv.addWidget(self.footer)
        h.addWidget(side)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.pages = {
            "achievements": AchievementsPage(app, self.icons),
            "planner": PlannerPage(app, self.icons),
            "playbooks": PlaybooksPage(app),
            "ingame": InGamePage(app),
            "assistant": AssistantPage(app),
            "settings": SettingsPage(app, self.syncer),
        }
        for key, _ in NAV:
            self.stack.addWidget(self.pages[key])
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.group.idClicked.connect(self.stack.setCurrentIndex)

        self.toast = Toast(self)
        app.toast.connect(self.toast.show_message)
        app.sync_changed.connect(self._footer)
        app.selection_changed.connect(self._footer)
        self.syncer.busy_changed.connect(lambda b: self.sync_btn.setText("⟳  Syncing…" if b else "⟳  Sync Steam"))

        p = self.pages
        p["achievements"].open_playbook.connect(lambda aid: self._goto("playbooks", p["playbooks"].show_achievement, aid))
        p["achievements"].ask_ai.connect(lambda aid: self._goto("assistant", p["assistant"].set_focus, aid))
        p["planner"].open_achievement.connect(lambda aid: self._goto("achievements", p["achievements"].select, aid))
        p["planner"].start_game.connect(lambda: self.show_page("ingame"))
        p["ingame"].ask_ai.connect(lambda name: self._goto("assistant", p["assistant"].send, QUICK_PROMPTS[name]))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)

        self.show_page("achievements" if app.synced_at else "settings")
        self._footer()
        if not app.synced_at:
            app.toast.emit("info", "Welcome. Enter your Steam profile and press Save & sync now.")

    def show_page(self, key: str) -> None:
        self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])

    def _goto(self, key: str, fn, arg) -> None:
        self.show_page(key)
        fn(arg)

    def _focus_search(self) -> None:
        self.show_page("achievements")
        self.pages["achievements"].search.setFocus()

    def _footer(self) -> None:
        self.footer.setText(f"{self.app.last_synced_text()}\n{len(self.app.selected)} target(s) in batch")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 24, self.height() - self.toast.height() - 24)
