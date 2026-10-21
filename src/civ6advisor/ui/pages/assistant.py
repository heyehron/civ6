"""AI assistant page: local Ollama chat with the app's context (batch, live state, playbook progress)."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QPlainTextEdit, QTextBrowser, QVBoxLayout, QWidget,
)

from ... import config
from ...ai import prompts
from ...ai.ollama import Message, OllamaClient, OllamaError
from ...ai.worker import ChatRunner
from ..appstate import AppState
from ..theme import C
from ..widgets import PageHeader, button, label

HISTORY_TURNS = 10
CHAT_FILE = config.HOME / "chat.json"


def md_to_html(text: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(text)
    out = doc.toHtml()
    m = re.search(r"<body[^>]*>(.*)</body>", out, re.S)
    return m.group(1) if m else html.escape(text)


class AssistantPage(QWidget):
    def __init__(self, app: AppState):
        super().__init__()
        self.app = app
        self.history: list[dict] = config.read_json(CHAT_FILE, [])
        self.focus: str | None = None
        self.streaming = ""
        self.runner = ChatRunner(self)
        self.runner.token.connect(self._token)
        self.runner.finished.connect(self._done)
        self.runner.failed.connect(self._failed)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.render)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        self.header = PageHeader("Assistant", "Runs on your PC through Ollama. Answers use your batch, live game "
                                              "state and playbook progress as context.")
        self.model = QComboBox()
        self.model.setMinimumWidth(200)
        self.model.setEditable(True)
        self.model.currentTextChanged.connect(self._model_changed)
        self.header.actions.addWidget(self.model)
        self.header.actions.addWidget(button("↻", "Ghost", tip="Refresh model list", slot=self.refresh_models))
        self.dot = label("●")
        self.header.actions.addWidget(self.dot)
        self.header.actions.addWidget(button("New chat", slot=self.clear))
        lay.addWidget(self.header)

        ctx = QHBoxLayout()
        ctx.addWidget(label("Context:", "Muted"))
        self.use_batch = QCheckBox("Batch")
        self.use_state = QCheckBox("Game state")
        self.use_progress = QCheckBox("Playbook progress")
        for cb in (self.use_batch, self.use_state, self.use_progress):
            cb.setChecked(True)
            ctx.addWidget(cb)
        self.focus_btn = button("", "Chip", slot=self._clear_focus)
        self.focus_btn.hide()
        ctx.addWidget(self.focus_btn)
        ctx.addStretch(1)
        self.shot = QCheckBox("Attach screenshot")
        self.shot.setToolTip("Sends a picture of your primary monitor. Needs a vision model such as qwen2.5vl. "
                             "Native full-screen games may capture as black.")
        ctx.addWidget(self.shot)
        lay.addLayout(ctx)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        for name, text in prompts.QUICK_PROMPTS.items():
            quick.addWidget(button(name, "Chip", tip=text, slot=lambda _=False, t=text: self.send(t)))
        quick.addStretch(1)
        lay.addLayout(quick)

        row = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Ask anything about your batch or game… (Ctrl+Enter to send)")
        self.input.setFixedHeight(76)
        row.addWidget(self.input, 1)
        col = QVBoxLayout()
        self.send_btn = button("Send", "Primary", slot=lambda: self.send())
        self.stop_btn = button("Stop", slot=self.runner.cancel)
        self.stop_btn.hide()
        col.addWidget(self.send_btn)
        col.addWidget(self.stop_btn)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row)
        QShortcut(QKeySequence("Ctrl+Return"), self.input, activated=self.send)

        app.settings_changed.connect(self.refresh_models)
        self.refresh_models()
        self.render()

    # Models -----------------------------------------------------------------------------
    def client(self) -> OllamaClient:
        s = self.app.settings
        return OllamaClient(s.ollama_url, s.ollama_model, s.temperature)

    def refresh_models(self) -> None:
        current = self.app.settings.ollama_model
        try:
            models = self.client().models()
            self.dot.setStyleSheet(f"color: {C['green']}; background: transparent;")
            self.dot.setToolTip(f"Ollama connected at {self.app.settings.ollama_url}")
        except OllamaError as exc:
            models = []
            self.dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
            self.dot.setToolTip(str(exc))
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(models or [current])
        self.model.setCurrentText(current)
        self.model.blockSignals(False)

    def _model_changed(self, name: str) -> None:
        if name and name != self.app.settings.ollama_model:
            self.app.settings.ollama_model = name
            self.app.settings.save()

    # Context ----------------------------------------------------------------------------
    def set_focus(self, aid: str) -> None:
        self.focus = aid
        self.focus_btn.setText(f"✕ {self.app.achievements[aid]['name']}")
        self.focus_btn.show()
        self.input.setPlainText(f"How do I get “{self.app.achievements[aid]['name']}”? Give a concrete plan.")
        self.input.setFocus()

    def _clear_focus(self) -> None:
        self.focus = None
        self.focus_btn.hide()

    def context(self) -> str:
        app = self.app
        parts = []
        if self.focus:
            a = app.achievements[self.focus]
            parts.append("Achievement the player is asking about:\n" +
                         prompts.achievement_brief(a, app.pct.get(self.focus), self.focus in app.unlocked))
            pb = app.playbooks.get(self.focus)
            if pb:
                parts.append("Existing playbook steps: " + "; ".join(s["text"] for s in pb["steps"]))
        if self.use_batch.isChecked():
            parts.append(prompts.batch_context(app.selected_achs(), app.leaders, app.pct, app.unlocked))
        if self.use_state.isChecked():
            parts.append(prompts.state_context(app.game_state))
        if self.use_progress.isChecked() and app.advice:
            parts.append(prompts.advice_context(app.advice))
        parts.append(f"Player stats: {len(app.unlocked)}/{len(app.achievements)} achievements unlocked.")
        return prompts.build_context(parts)

    def _screenshot(self) -> bytes | None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        pm = screen.grabWindow(0)
        if pm.width() > 1600:
            pm = pm.scaledToWidth(1600, Qt.SmoothTransformation)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        pm.save(buf, "PNG")
        return bytes(data)

    # Chat -------------------------------------------------------------------------------
    def send(self, text: str | None = None) -> None:
        if self.runner.busy:
            return
        text = (text or self.input.toPlainText()).strip()
        if not text:
            return
        self.input.clear()
        images = None
        if self.shot.isChecked():
            img = self._screenshot()
            images = [img] if img else None
        self.history.append({"role": "user", "content": text, "image": bool(images)})
        msgs = [Message("system", prompts.SYSTEM)]
        ctx = self.context()
        if ctx:
            msgs.append(Message("system", ctx))
        for h in self.history[-HISTORY_TURNS * 2:-1]:
            if h["role"] in ("user", "assistant"):
                msgs.append(Message(h["role"], h["content"]))
        msgs.append(Message("user", text, images))
        self.streaming = ""
        self.send_btn.setEnabled(False)
        self.stop_btn.show()
        self.runner.start(self.client(), msgs)
        self.render()

    def _token(self, piece: str) -> None:
        self.streaming += piece
        if not self._render_timer.isActive():
            self._render_timer.start(70)

    def _finish(self, reply: str | None, error: str | None = None) -> None:
        self.send_btn.setEnabled(True)
        self.stop_btn.hide()
        if reply:
            self.history.append({"role": "assistant", "content": reply})
        if error:
            self.history.append({"role": "error", "content": error})
        self.streaming = ""
        config.write_json(CHAT_FILE, self.history[-60:])
        self.render()

    def _done(self, text: str) -> None:
        self._finish(text)

    def _failed(self, msg: str) -> None:
        self._finish(self.streaming or None, msg)

    def clear(self) -> None:
        if self.runner.busy:
            self.runner.cancel()
        self.history = []
        config.write_json(CHAT_FILE, [])
        self.render()

    def render(self) -> None:
        rows = []
        if not self.history and not self.runner.busy:
            rows.append(f"<p style='color:{C['muted']}'>Ask about your batch, a specific achievement, or what to do "
                        f"this turn. Use the quick prompts below to start. Model: "
                        f"<b>{html.escape(self.app.settings.ollama_model)}</b>.</p>")
        items = list(self.history)
        if self.runner.busy:
            items.append({"role": "assistant", "content": self.streaming or "…", "live": True})
        for h in items:
            role = h["role"]
            if role == "user":
                who, bg, colour = "You", C["surface2"], C["gold_hi"]
                body = html.escape(h["content"]).replace("\n", "<br>")
                if h.get("image"):
                    body += f"<br><span style='color:{C['faint']}'>[screenshot attached]</span>"
            elif role == "error":
                who, bg, colour = "Error", "#3a1f22", C["red"]
                body = html.escape(h["content"])
            else:
                who, bg, colour = "Advisor", C["surface"], C["blue"]
                body = md_to_html(h["content"])
            rows.append(f"<table width='100%' cellpadding='10' style='margin:6px 0'><tr>"
                        f"<td style='background:{bg};border-radius:8px'>"
                        f"<p style='color:{colour};font-weight:700;font-size:11px;margin:0 0 4px 0'>{who.upper()}</p>{body}"
                        f"</td></tr></table>")
        self.view.setHtml("".join(rows))
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())
