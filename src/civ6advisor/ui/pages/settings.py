"""Settings page: Steam, game log, local AI, planner weights, HUD."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from ... import config
from ...ai.ollama import OllamaClient, OllamaError
from ...engine.batch import DIFFICULTIES
from ...steam import sync as steam
from ..appstate import AppState
from ..theme import C
from ..widgets import Card, PageHeader, button, label


class _SyncJob(QObject):
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


class SteamSync(QObject):
    """Runs a Steam sync on a worker thread and applies it to the app state."""
    busy_changed = Signal(bool)

    def __init__(self, app: AppState, parent=None):
        super().__init__(parent)
        self.app = app
        self._thread: QThread | None = None

    def start(self) -> None:
        profile = self.app.settings.profile.strip()
        if not profile:
            self.app.toast.emit("warning", "Set your Steam profile in Settings first.")
            return
        if self._thread and self._thread.isRunning():
            return
        self._thread = QThread(self)
        self._job = _SyncJob(profile)
        self._job.moveToThread(self._thread)
        self._thread.started.connect(self._job.run)
        self._job.done.connect(self._ok)
        self._job.failed.connect(self._fail)
        self._job.done.connect(self._thread.quit)
        self._job.failed.connect(self._thread.quit)
        self.busy_changed.emit(True)
        self._thread.start()

    def _ok(self, res) -> None:
        self.busy_changed.emit(False)
        self.app.apply_sync(res)
        msg = "Loaded cached data (Steam unreachable)" if res.from_cache else \
            f"Synced: {len(res.unlocked)} unlocked"
        self.app.toast.emit("warning" if res.from_cache else "success", msg)

    def _fail(self, msg: str) -> None:
        self.busy_changed.emit(False)
        self.app.toast.emit("error", msg)


class SettingsPage(QScrollArea):
    def __init__(self, app: AppState, syncer: SteamSync):
        super().__init__()
        self.app, self.syncer = app, syncer
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        self.setWidget(host)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(PageHeader("Settings", "Stored in ~/.civ6advisor. Nothing here is committed to git."))
        s = app.settings
        grid = QGridLayout()
        grid.setSpacing(14)

        steam_card = Card("Steam")
        f = QFormLayout()
        self.profile = QLineEdit(s.profile)
        self.profile.setPlaceholderText("Custom URL name (e.g. NobodyYouKnow) or SteamID64")
        f.addRow("Profile", self.profile)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("stored in keyring" if steam.api_key() else "optional — not needed")
        f.addRow("Web API key", self.key)
        steam_card.body.addLayout(f)
        steam_card.body.addWidget(label("Your profile's Game details must be Public. Without a key the app reads "
                                        "the public achievements page.", "Faint", wrap=True))
        row = QHBoxLayout()
        self.sync_btn = button("Save && sync now", "Primary", slot=self._sync)
        row.addWidget(self.sync_btn)
        row.addWidget(button("Forget API key", "Ghost", slot=self._forget_key))
        row.addStretch(1)
        steam_card.body.addLayout(row)
        syncer.busy_changed.connect(lambda b: self.sync_btn.setEnabled(not b))
        grid.addWidget(steam_card, 0, 0)

        ai = Card("Local AI (Ollama)")
        f = QFormLayout()
        self.url = QLineEdit(s.ollama_url)
        f.addRow("Server", self.url)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItem(s.ollama_model)
        f.addRow("Model", self.model)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 1.5)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(s.temperature)
        f.addRow("Temperature", self.temp)
        ai.body.addLayout(f)
        self.ai_status = label("", "Muted", wrap=True)
        ai.body.addWidget(self.ai_status)
        row = QHBoxLayout()
        row.addWidget(button("Test connection", slot=self._test_ai))
        row.addStretch(1)
        ai.body.addLayout(row)
        ai.body.addWidget(label("qwen2.5vl:3b reads screenshots and fits next to Civ in 8 GB VRAM. For pre-game "
                                "planning a larger text model (e.g. qwen2.5:7b) gives better plans; close Civ first.",
                                "Faint", wrap=True))
        grid.addWidget(ai, 0, 1)

        game = Card("Game log")
        f = QFormLayout()
        self.log = QLineEdit(s.lua_log)
        prow = QHBoxLayout()
        prow.addWidget(self.log, 1)
        prow.addWidget(button("Browse", slot=self._browse))
        f.addRow("Lua.log", prow)
        game.body.addLayout(f)
        self.log_status = label("", "Faint", wrap=True)
        game.body.addWidget(self.log_status)
        game.body.addWidget(label("Install the advisor mod from the repo's mod/ folder into "
                                  "Documents/My Games/Sid Meier's Civilization VI/Mods and enable it under "
                                  "Additional Content.", "Faint", wrap=True))
        grid.addWidget(game, 1, 0)

        plan = Card("Planner")
        f = QFormLayout()
        self.max_diff = QComboBox()
        self.max_diff.addItems([d.title() for d in DIFFICULTIES])
        self.max_diff.setCurrentText(s.max_difficulty.title())
        f.addRow("Highest difficulty you'd play", self.max_diff)
        self.w_rarity = self._spin(s.weight_rarity)
        self.w_overlap = self._spin(s.weight_overlap)
        self.w_risk = self._spin(s.weight_risk)
        f.addRow("Weight: rarity", self.w_rarity)
        f.addRow("Weight: shared settings", self.w_overlap)
        f.addRow("Weight: risk penalty", self.w_risk)
        plan.body.addLayout(f)
        plan.body.addWidget(label("Fit score = rarity × w₁ + targets sharing a setting × w₂ − risk × w₃",
                                  "Faint", wrap=True))
        grid.addWidget(plan, 1, 1)

        hud = Card("HUD")
        f = QFormLayout()
        self.screen = QComboBox()
        self.screen.addItem("Auto (first non-primary)")
        for i, sc in enumerate(QGuiApplication.screens()):
            g = sc.geometry()
            self.screen.addItem(f"{i + 1}: {sc.name()} {g.width()}×{g.height()}"
                                f"{' (primary)' if sc is QGuiApplication.primaryScreen() else ''}")
        self.screen.setCurrentIndex(s.hud_screen + 1 if s.hud_screen >= 0 else 0)
        f.addRow("Monitor", self.screen)
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.4, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(s.hud_opacity)
        f.addRow("Opacity", self.opacity)
        hud.body.addLayout(f)
        grid.addWidget(hud, 2, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        save = button("Save settings", "Primary", slot=self.save)
        save.setMinimumWidth(180)
        lay.addWidget(save, 0, Qt.AlignRight)
        lay.addStretch(1)
        self._check_log()

    @staticmethod
    def _spin(v: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0, 5)
        sp.setSingleStep(0.1)
        sp.setValue(v)
        return sp

    def _check_log(self) -> None:
        p = Path(self.log.text())
        self.log_status.setText("✓ Found" if p.exists() else "Not found yet — it appears after Civ VI runs once with "
                                                             "logging enabled.")
        self.log_status.setStyleSheet(f"color: {C['green'] if p.exists() else C['amber']}; background: transparent;")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Lua.log", self.log.text(), "Log (*.log);;All files (*)")
        if path:
            self.log.setText(path)
            self._check_log()

    def save(self) -> None:
        s = self.app.settings
        s.profile = self.profile.text().strip()
        s.ollama_url = self.url.text().strip() or "http://localhost:11434"
        s.ollama_model = self.model.currentText().strip() or s.ollama_model
        s.temperature = self.temp.value()
        s.lua_log = self.log.text().strip()
        s.max_difficulty = self.max_diff.currentText().lower()
        s.weight_rarity, s.weight_overlap, s.weight_risk = (self.w_rarity.value(), self.w_overlap.value(),
                                                            self.w_risk.value())
        s.hud_screen = self.screen.currentIndex() - 1
        s.hud_opacity = self.opacity.value()
        if self.key.text().strip():
            try:
                steam.set_api_key(self.key.text().strip())
                self.key.clear()
                self.key.setPlaceholderText("stored in keyring")
            except Exception as exc:
                self.app.toast.emit("error", f"Could not store the key: {exc}")
        self.app.save_settings()
        self._check_log()
        self.app.toast.emit("success", "Settings saved")

    def _sync(self) -> None:
        self.save()
        self.syncer.start()

    def _forget_key(self) -> None:
        try:
            steam.set_api_key(None)
        except Exception:
            pass
        self.key.setPlaceholderText("optional — not needed")
        self.app.toast.emit("info", "API key removed")

    def _test_ai(self) -> None:
        client = OllamaClient(self.url.text().strip(), self.model.currentText().strip())
        try:
            models = client.models()
        except OllamaError as exc:
            self.ai_status.setText(f"✖ {exc}")
            self.ai_status.setStyleSheet(f"color: {C['red']}; background: transparent;")
            return
        current = self.model.currentText()
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(current)
        ok = current in models
        self.ai_status.setText(f"✓ Connected · {len(models)} model(s)" + ("" if ok else
                               f" · '{current}' not installed: run  ollama pull {current}"))
        self.ai_status.setStyleSheet(f"color: {C['green'] if ok else C['amber']}; background: transparent;")
