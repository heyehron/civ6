import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from civ6advisor.ui.appstate import AppState
from civ6advisor.ui.hud import Hud


def test_hud_has_native_frame_and_remembers_position(tmp_path, monkeypatch):
    monkeypatch.setenv("CIV6ADVISOR_HOME", str(tmp_path))
    import importlib

    from civ6advisor import config
    importlib.reload(config)
    app = QApplication.instance() or QApplication([])
    state = AppState()
    hud = Hud(state)
    assert not hud.windowFlags() & Qt.FramelessWindowHint  # draggable by its title bar
    assert hud.windowFlags() & Qt.WindowStaysOnTopHint
    hud.setGeometry(QRect(60, 70, 480, 500))
    hud._save_geometry()
    assert state.settings.hud_geometry == [60, 70, 480, 500]
    hud2 = Hud(state)
    hud2.place()
    assert hud2.geometry().size().width() == 480
    hud2.place(reset=True)
    assert hud2.geometry().width() != 480 or hud2.geometry().x() != 60
