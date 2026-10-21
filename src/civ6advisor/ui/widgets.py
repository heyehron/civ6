"""Reusable widgets: cards, badges, page headers, toasts and the Steam icon cache."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import config
from .theme import C


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def button(text: str, kind: str | None = None, tip: str | None = None, slot=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, title: str | None = None, name: str = "Card", parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(label(title, "SectionTitle"))


class Badge(QLabel):
    def __init__(self, text: str, colour: str, filled: bool = False, parent=None):
        super().__init__(text, parent)
        bg = colour if filled else "transparent"
        fg = "#15120a" if filled else colour
        self.setStyleSheet(f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {colour};"
                           f" border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(title, "PageTitle"))
        self.sub = label(subtitle, "PageSub", wrap=True)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)


class EmptyState(QWidget):
    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        t = label(title, "Big")
        t.setAlignment(Qt.AlignCenter)
        b = label(text, "Muted", wrap=True)
        b.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(b)
        lay.addStretch(1)


class Toast(QLabel):
    """Transient message in the bottom-right corner of the main window."""
    COLOURS = {"info": C["blue"], "success": C["green"], "warning": C["amber"], "error": C["red"]}

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.hide()
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.fade_in = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade_in.setDuration(160)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_out = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade_out.setDuration(400)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self.hide)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade)

    def show_message(self, level: str, text: str, ms: int = 4200) -> None:
        colour = self.COLOURS.get(level, C["blue"])
        self.setStyleSheet(f"#Toast {{ border-left: 4px solid {colour}; }}")
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(p.width() - self.width() - 24, p.height() - self.height() - 24)
        self.raise_()
        self.show()
        self.fade_out.stop()
        self.fade_in.start()
        self.timer.start(ms)

    def _fade(self) -> None:
        self.fade_out.start()


def placeholder_icon(size: int, text: str = "?") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(C["surface2"]))
    p.setPen(QColor(C["border"]))
    p.drawRoundedRect(0, 0, size - 1, size - 1, 6, 6)
    p.setPen(QColor(C["faint"]))
    p.drawText(pm.rect(), Qt.AlignCenter, text[:1].upper())
    p.end()
    return pm


class IconCache(QObject):
    """Downloads Steam achievement icons once into ~/.civ6advisor/assets/icons (SPEC §4.8)."""
    loaded = Signal(str)  # achievement id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        self.mem: dict[str, QPixmap] = {}
        self.pending: set[str] = set()
        self.failed: set[str] = set()
        config.ICON_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, aid: str) -> Path:
        return config.ICON_DIR / f"{aid}.jpg"

    def get(self, aid: str, url: str | None) -> QPixmap | None:
        if aid in self.mem:
            return self.mem[aid]
        path = self._path(aid)
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                self.mem[aid] = pm
                return pm
        if url and aid not in self.pending and aid not in self.failed and len(self.pending) < 24:
            self.pending.add(aid)
            reply = self.net.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda r=reply, a=aid: self._done(r, a))
        return None

    def _done(self, reply: QNetworkReply, aid: str) -> None:
        self.pending.discard(aid)
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll().data()
            pm = QPixmap()
            if pm.loadFromData(data):
                self._path(aid).write_bytes(data)
                self.mem[aid] = pm
                self.loaded.emit(aid)
        else:
            self.failed.add(aid)
        reply.deleteLater()


class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto new lines (for badges and chips)."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self.items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self.items.append(item)

    def count(self) -> int:
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._do(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self.items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _do(self, rect, dry: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self.items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() and line > 0:
                x, y, line = rect.x(), y + line + sp, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + sp
            line = max(line, hint.height())
        return y + line - rect.y()


def clear_layout(layout) -> None:
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
        elif it.layout():
            clear_layout(it.layout())


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C['border']};")
    return f
