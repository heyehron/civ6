"""Civ VI Achievement Advisor entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ6advisor.dataset import load_achievements, load_leaders  # noqa: E402
from civ6advisor.ui.pregame import PreGameWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    win = PreGameWindow(load_achievements(), load_leaders())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
