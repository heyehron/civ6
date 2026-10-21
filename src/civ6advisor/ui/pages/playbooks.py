"""Playbooks page: browse, edit (JSON with live validation and preview), and draft with the local AI."""
from __future__ import annotations

import html
import json

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from ...ai import prompts
from ...ai.ollama import Message, OllamaClient, extract_json
from ...ai.worker import ChatRunner
from ...engine import playbook
from ..appstate import AppState
from ..theme import C
from ..widgets import PageHeader, button, label


def cond_text(cond) -> str:
    if not cond:
        return ""
    if "all" in cond:
        return " AND ".join(f"({cond_text(c)})" for c in cond["all"])
    if "any" in cond:
        return " OR ".join(f"({cond_text(c)})" for c in cond["any"])
    if "not" in cond:
        return f"NOT ({cond_text(cond['not'])})"
    ops = {"eq": "=", "ne": "≠", "lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "contains": "contains",
           "not_contains": "lacks", "count_gte": "count ≥", "exists": "is set", "in": "in"}
    val = "" if cond["op"] == "exists" else json.dumps(cond.get("value"), ensure_ascii=False)
    return f"{cond['field']} {ops.get(cond['op'], cond['op'])} {val}".strip()


def render_html(pb: dict) -> str:
    parts = [f"<h2 style='color:{C['gold_hi']};margin:0'>{html.escape(pb.get('title', pb.get('achievement', '')))}</h2>"]
    if pb.get("summary"):
        parts.append(f"<p style='color:{C['muted']}'>{html.escape(pb['summary'])}</p>")
    author = pb.get("author", "hand")
    tag = {"auto": "auto-generated setup checks", "ai-draft": "AI draft"}.get(author, "hand-written")
    parts.append(f"<p style='color:{C['faint']}'>{tag}{' · verified' if pb.get('verified') else ' · unverified'}</p>")
    for i, st in enumerate(pb.get("steps", []), 1):
        track = "manual tick" if st.get("manual") else "auto-tracked"
        dl = f" · by turn {st['deadline_turn']}" if st.get("deadline_turn") else ""
        parts.append(f"<div style='margin:10px 0;padding:8px 10px;background:{C['surface2']};border-radius:8px'>"
                     f"<b>{i}. {html.escape(st.get('text', ''))}</b>"
                     f"<span style='color:{C['faint']}'> &nbsp;{track}{dl}</span>")
        if st.get("detail"):
            parts.append(f"<br><span style='color:{C['muted']}'>{html.escape(st['detail'])}</span>")
        if st.get("done_when"):
            parts.append(f"<br><span style='color:{C['green']}'>done when</span> "
                         f"<code>{html.escape(cond_text(st['done_when']))}</code>")
        if st.get("fail_when"):
            parts.append(f"<br><span style='color:{C['red']}'>fails when</span> "
                         f"<code>{html.escape(cond_text(st['fail_when']))}</code>")
        parts.append("</div>")
    if pb.get("tips"):
        parts.append(f"<h3 style='color:{C['muted']}'>Tips</h3><ul>")
        parts += [f"<li>{html.escape(t)}</li>" for t in pb["tips"]]
        parts.append("</ul>")
    return "".join(parts)


class PlaybooksPage(QWidget):
    open_achievement = Signal(str)

    def __init__(self, app: AppState):
        super().__init__()
        self.app = app
        self.current: str | None = None
        self.runner = ChatRunner(self)
        self.runner.token.connect(self._ai_token)
        self.runner.finished.connect(self._ai_done)
        self.runner.failed.connect(self._ai_failed)
        self._ai_buffer = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.header = PageHeader("Playbooks", "Ordered steps per achievement, checked live against the game. "
                                               "Achievements without one get automatic setup checks.")
        lay.addWidget(self.header)

        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_list)
        lv.addWidget(self.search)
        chips = QHBoxLayout()
        self.scope = {}
        for key, text in (("batch", "Batch"), ("written", "Written"), ("locked", "All locked")):
            b = button(text, "Chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._set_scope(k))
            self.scope[key] = b
            chips.addWidget(b)
        chips.addStretch(1)
        lv.addLayout(chips)
        self.scope_key = "batch"
        self.scope["batch"].setChecked(True)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._picked)
        lv.addWidget(self.list, 1)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.title = label("Select an achievement", "Big")
        bar.addWidget(self.title, 1)
        self.repo_box = QCheckBox("Save into repo")
        self.repo_box.setToolTip("Write to data/playbooks (commit it to share). Otherwise saved to ~/.civ6advisor/playbooks")
        bar.addWidget(self.repo_box)
        self.save_btn = button("Save", "Primary", slot=self._save)
        bar.addWidget(self.save_btn)
        bar.addWidget(button("Reset to auto", "Ghost", slot=self._reset_auto))
        rv.addLayout(bar)

        ai_bar = QHBoxLayout()
        self.ai_extra = QLineEdit()
        self.ai_extra.setPlaceholderText("Optional instructions for the AI, e.g. 'assume Emperor, Duel map'")
        ai_bar.addWidget(self.ai_extra, 1)
        self.draft_btn = button("✦ Draft with AI", slot=self._draft)
        self.improve_btn = button("✦ Improve with AI", slot=self._improve)
        self.stop_btn = button("Stop", "Ghost", slot=self.runner.cancel)
        self.stop_btn.hide()
        for b in (self.draft_btn, self.improve_btn, self.stop_btn):
            ai_bar.addWidget(b)
        rv.addLayout(ai_bar)

        self.tabs = QTabWidget()
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.editor = QPlainTextEdit()
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self.editor.setFont(mono)
        self.editor.textChanged.connect(lambda: self._validate_timer.start(300))
        self.tabs.addTab(self.preview, "Preview")
        self.tabs.addTab(self.editor, "JSON")
        rv.addWidget(self.tabs, 1)
        self.problems = label("", wrap=True)
        rv.addWidget(self.problems)
        self.fields_help = QTextBrowser()
        self.fields_help.setMaximumHeight(130)
        self.fields_help.setHtml("<b>Fields you can use</b><br>" + "<br>".join(
            f"<code>{k}</code> <span style='color:{C['muted']}'>{html.escape(v)}</span>"
            for k, v in prompts.FIELD_CATALOG.items()) +
            f"<br><b>Ops</b>: {', '.join(playbook.OPS)}")
        rv.addWidget(self.fields_help)
        split.addWidget(right)
        split.setSizes([330, 900])
        lay.addWidget(split, 1)

        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.timeout.connect(self._validate)
        app.playbooks_changed.connect(self.refresh_list)
        app.selection_changed.connect(self.refresh_list)
        app.sync_changed.connect(self.refresh_list)
        self.refresh_list()

    # List -------------------------------------------------------------------------------
    def _set_scope(self, key: str) -> None:
        self.scope_key = key
        for k, b in self.scope.items():
            b.setChecked(k == key)
        self.refresh_list()

    def refresh_list(self) -> None:
        app = self.app
        if self.scope_key == "batch":
            ids = list(app.selected)
        elif self.scope_key == "written":
            ids = [i for i in app.playbooks if i in app.achievements]
        else:
            ids = sorted(app.locked, key=lambda i: app.pct.get(i, 999))
        needle = self.search.text().lower().strip()
        self.list.blockSignals(True)
        self.list.clear()
        for aid in ids:
            a = app.achievements[aid]
            if needle and needle not in a["name"].lower():
                continue
            pb = app.playbooks.get(aid)
            tag = "auto" if not pb else ("AI draft" if pb.get("author") == "ai-draft" else "written")
            item = QListWidgetItem(f"{a['name']}\n{tag}")
            item.setData(Qt.UserRole, aid)
            item.setForeground(QColor(C["text"] if pb else C["muted"]))
            self.list.addItem(item)
            if aid == self.current:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.list.count() == 0:
            self.list.addItem(QListWidgetItem("Nothing here yet" if self.scope_key != "batch"
                                              else "Your batch is empty"))

    def _picked(self, item, _prev) -> None:
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.load(item.data(Qt.UserRole))

    def load(self, aid: str) -> None:
        self.current = aid
        pb = self.app.playbook_for(aid)
        data = {k: v for k, v in pb.items() if not k.startswith("_")}
        self.title.setText(self.app.achievements[aid]["name"])
        self.editor.setPlainText(json.dumps(data, indent=1, ensure_ascii=False))
        self._validate()

    def show_achievement(self, aid: str) -> None:
        if aid not in self.app.selected and aid not in self.app.playbooks:
            self._set_scope("locked")
        self.load(aid)
        self.refresh_list()

    # Editing ----------------------------------------------------------------------------
    def _parsed(self) -> tuple[dict | None, list[str]]:
        try:
            pb = json.loads(self.editor.toPlainText())
        except ValueError as exc:
            return None, [f"JSON error: {exc}"]
        return pb, playbook.validate(pb)

    def _validate(self) -> None:
        pb, errs = self._parsed()
        if pb is not None:
            self.preview.setHtml(render_html(pb))
        if errs:
            self.problems.setText("⚠ " + "\n⚠ ".join(errs[:6]))
            self.problems.setStyleSheet(f"color: {C['red']}; background: transparent;")
        else:
            self.problems.setText("✓ Valid playbook")
            self.problems.setStyleSheet(f"color: {C['green']}; background: transparent;")
        self.save_btn.setEnabled(not errs and self.current is not None)

    def _save(self) -> None:
        pb, errs = self._parsed()
        if errs or pb is None or not self.current:
            return
        pb["achievement"] = self.current
        if pb.get("author") == "auto":
            pb["author"] = "hand"
        self.app.save_playbook(pb, to_repo=self.repo_box.isChecked())
        self.app.toast.emit("success", "Playbook saved" + (" to data/playbooks" if self.repo_box.isChecked() else ""))

    def _reset_auto(self) -> None:
        if not self.current:
            return
        pb = playbook.auto_playbook(self.app.achievements[self.current], self.app.leaders)
        self.editor.setPlainText(json.dumps(pb, indent=1, ensure_ascii=False))

    # AI ---------------------------------------------------------------------------------
    def _client(self) -> OllamaClient:
        s = self.app.settings
        return OllamaClient(s.ollama_url, s.ollama_model, min(s.temperature, 0.3))

    def _start_ai(self, user: str) -> None:
        if self.runner.busy or not self.current:
            return
        self._ai_buffer = ""
        self._before_ai = self.editor.toPlainText()
        self.editor.setPlainText("")
        self.tabs.setCurrentWidget(self.editor)
        self.draft_btn.setEnabled(False)
        self.improve_btn.setEnabled(False)
        self.stop_btn.show()
        msgs = [Message("system", prompts.SYSTEM), Message("user", user)]
        self.runner.start(self._client(), msgs, json_mode=True)

    def _draft(self) -> None:
        if not self.current:
            return
        a = self.app.achievements[self.current]
        extra = self.ai_extra.text().strip()
        ctx = prompts.batch_context(self.app.selected_achs(), self.app.leaders, self.app.pct, self.app.unlocked)
        self._start_ai(prompts.playbook_prompt(a, f"\nPlayer's current batch, for context:\n{ctx}\n"
                                                  f"{'Extra instructions: ' + extra if extra else ''}"))

    def _improve(self) -> None:
        if not self.current:
            return
        a = self.app.achievements[self.current]
        extra = self.ai_extra.text().strip() or "Make the steps more concrete and trackable."
        self._start_ai(prompts.playbook_prompt(a) + "\n\nImprove this existing playbook. Keep valid steps, fix "
                       f"invalid fields, and follow these instructions: {extra}\n\n{self.editor.toPlainText()}")

    def _ai_token(self, piece: str) -> None:
        self._ai_buffer += piece
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(piece, QTextCharFormat())
        self.editor.setTextCursor(cur)

    def _ai_end(self) -> None:
        self.draft_btn.setEnabled(True)
        self.improve_btn.setEnabled(True)
        self.stop_btn.hide()

    def _ai_done(self, text: str) -> None:
        self._ai_end()
        obj = extract_json(text)
        if obj is None:
            self.app.toast.emit("error", "The AI reply was not valid JSON. Your previous text is restored.")
            self.editor.setPlainText(self._before_ai)
            return
        obj["achievement"] = self.current
        obj["author"] = "ai-draft"
        obj["verified"] = False
        self.editor.setPlainText(json.dumps(obj, indent=1, ensure_ascii=False))
        self._validate_timer.stop()
        self._validate()
        self.tabs.setCurrentWidget(self.preview)
        errs = playbook.validate(obj)
        self.app.toast.emit("warning" if errs else "success",
                            f"AI draft ready with {len(errs)} problem(s) to fix" if errs else
                            "AI draft ready. Review it, then Save.")

    def _ai_failed(self, msg: str) -> None:
        self._ai_end()
        self.editor.setPlainText(self._before_ai)
        self.app.toast.emit("error", msg)
