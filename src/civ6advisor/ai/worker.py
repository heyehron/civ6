"""Qt worker that streams an Ollama reply without blocking the UI."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from .ollama import Message, OllamaClient, OllamaError


class _ChatJob(QObject):
    token = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, client: OllamaClient, messages: list[Message], json_mode: bool):
        super().__init__()
        self.client, self.messages, self.json_mode = client, messages, json_mode
        self.cancelled = False

    def run(self) -> None:
        out: list[str] = []
        try:
            for piece in self.client.chat_stream(self.messages, self.json_mode, cancel=lambda: self.cancelled):
                out.append(piece)
                self.token.emit(piece)
        except OllamaError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # network edge cases inside requests' iterator
            self.failed.emit(f"Unexpected error: {exc}")
            return
        self.finished.emit("".join(out))


class ChatRunner(QObject):
    """Owns one background thread per request. Emits token / finished / failed."""
    token = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._job: _ChatJob | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, client: OllamaClient, messages: list[Message], json_mode: bool = False) -> None:
        if self.busy:
            return
        self._thread = QThread(self)
        self._job = _ChatJob(client, messages, json_mode)
        self._job.moveToThread(self._thread)
        self._thread.started.connect(self._job.run)
        self._job.token.connect(self.token)
        self._job.finished.connect(self.finished)
        self._job.failed.connect(self.failed)
        self._job.finished.connect(self._thread.quit)
        self._job.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def cancel(self) -> None:
        if self._job:
            self._job.cancelled = True

    def _cleanup(self) -> None:
        if self._job:
            self._job.deleteLater()
        if self._thread:
            self._thread.deleteLater()
        self._job = None
        self._thread = None
