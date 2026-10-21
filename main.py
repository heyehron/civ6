"""Civ VI Achievement Advisor entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ6advisor.ui import theme  # noqa: E402
from civ6advisor.ui.appstate import AppState  # noqa: E402
from civ6advisor.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Civ VI Achievement Advisor")
    theme.apply(app)
    state = AppState()
    win = MainWindow(state)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
