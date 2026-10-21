"""Dark theme with a Civ-style gold accent."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

C = {
    "bg": "#12151a",
    "panel": "#181c23",
    "surface": "#1f252e",
    "surface2": "#262d38",
    "border": "#2e3643",
    "text": "#e7e9ee",
    "muted": "#9099a8",
    "faint": "#5d6675",
    "gold": "#d9a441",
    "gold_hi": "#f0c060",
    "red": "#e5676f",
    "amber": "#e8a33d",
    "green": "#79c288",
    "blue": "#6aaeea",
    "purple": "#b48ce6",
}

LABEL_COLOURS = {"Required": C["red"], "Recommended": C["blue"], "Free": C["faint"]}
CONTENT_COLOURS = {
    "base": C["muted"], "rise_and_fall": C["amber"], "gathering_storm": C["blue"],
    "new_frontier": C["green"], "leader_pack": C["purple"], "scenario": C["gold"],
}


def rarity_colour(pct: float | None) -> str:
    if pct is None:
        return C["faint"]
    if pct < 1:
        return C["gold_hi"]
    if pct < 5:
        return C["purple"]
    if pct < 15:
        return C["blue"]
    return C["muted"]


QSS = f"""
* {{ outline: 0; }}
QWidget {{ background: {C['bg']}; color: {C['text']}; font-size: 13px; }}
QMainWindow, #Content {{ background: {C['bg']}; }}
#Sidebar {{ background: {C['panel']}; border-right: 1px solid {C['border']}; }}
#Brand {{ color: {C['gold']}; font-size: 17px; font-weight: 700; padding: 18px 16px 4px 16px; background: transparent; }}
#BrandSub {{ color: {C['muted']}; font-size: 11px; padding: 0 16px 14px 16px; background: transparent; }}
#NavButton {{ background: transparent; border: none; border-left: 3px solid transparent; color: {C['muted']};
             text-align: left; padding: 10px 16px; font-size: 13px; }}
#NavButton:hover {{ color: {C['text']}; background: {C['surface']}; }}
#NavButton:checked {{ color: {C['gold_hi']}; background: {C['surface']}; border-left: 3px solid {C['gold']}; font-weight: 600; }}
#SidebarFooter {{ color: {C['faint']}; font-size: 11px; padding: 12px 16px; background: transparent; }}

#PageTitle {{ font-size: 22px; font-weight: 700; background: transparent; }}
#PageSub {{ color: {C['muted']}; background: transparent; }}
#SectionTitle {{ color: {C['muted']}; font-size: 11px; font-weight: 700; letter-spacing: 1px;
                text-transform: uppercase; background: transparent; padding-top: 4px; }}
#Card {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; }}
#Card QLabel, #Card QCheckBox {{ background: transparent; }}
#Hero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2a2416, stop:1 {C['surface']});
         border: 1px solid #4a3d1f; border-radius: 12px; }}
#Hero QLabel {{ background: transparent; }}
#HeroText {{ font-size: 22px; font-weight: 700; color: {C['gold_hi']}; }}
#Muted {{ color: {C['muted']}; background: transparent; }}
#Faint {{ color: {C['faint']}; background: transparent; }}
#Big {{ font-size: 18px; font-weight: 700; background: transparent; }}

QPushButton {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 7px;
               padding: 7px 14px; color: {C['text']}; }}
QPushButton:hover {{ border-color: {C['gold']}; }}
QPushButton:pressed {{ background: {C['surface']}; }}
QPushButton:disabled {{ color: {C['faint']}; border-color: {C['border']}; }}
QPushButton#Primary {{ background: {C['gold']}; color: #1a1408; border: 1px solid {C['gold']}; font-weight: 700; }}
QPushButton#Primary:hover {{ background: {C['gold_hi']}; }}
QPushButton#Primary:disabled {{ background: {C['surface2']}; color: {C['faint']}; border-color: {C['border']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {C['muted']}; padding: 5px 8px; }}
QPushButton#Ghost:hover {{ color: {C['text']}; border-color: {C['border']}; }}
QPushButton#Chip {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 13px;
                    padding: 4px 12px; color: {C['muted']}; }}
QPushButton#Chip:checked {{ background: #3a301a; border-color: {C['gold']}; color: {C['gold_hi']}; }}
QPushButton#Chip:hover {{ color: {C['text']}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {C['panel']}; border: 1px solid {C['border']}; border-radius: 7px; padding: 6px 8px;
    selection-background-color: {C['gold']}; selection-color: #1a1408; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {C['gold']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QComboBox QAbstractItemView {{ background: {C['surface']}; border: 1px solid {C['border']};
    selection-background-color: {C['surface2']}; selection-color: {C['gold_hi']}; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {C['faint']}; background: {C['panel']}; }}
QCheckBox::indicator:checked {{ background: {C['gold']}; border-color: {C['gold']}; }}
QTreeView::indicator, QTableView::indicator, QListView::indicator {{ width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {C['faint']}; background: {C['panel']}; }}
QTreeView::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {{
    background: {C['gold']}; border-color: {C['gold']}; }}
QTreeView::item {{ padding: 5px 2px; }}

QTableView, QTreeView, QListView, QListWidget, QTableWidget {{
    background: {C['panel']}; alternate-background-color: #1b2028; border: 1px solid {C['border']};
    border-radius: 8px; gridline-color: transparent; selection-background-color: #2c2a22;
    selection-color: {C['text']}; }}
QTableView::item, QTableWidget::item {{ padding: 4px 6px; border: none; }}
QTableView::item:selected, QTableWidget::item:selected {{ background: #2f2a1c; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #2f2a1c; color: {C['gold_hi']}; }}
QListWidget::item:hover {{ background: {C['surface']}; }}
QHeaderView::section {{ background: {C['panel']}; color: {C['muted']}; border: none;
    border-bottom: 1px solid {C['border']}; padding: 7px 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {C['panel']}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['surface2']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C['surface2']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {C['panel']}; border: 1px solid {C['border']}; border-radius: 5px; height: 10px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {C['gold']}; border-radius: 4px; }}
QSplitter::handle {{ background: {C['bg']}; width: 8px; }}
QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 8px; top: -1px; background: {C['surface']}; }}
QTabBar::tab {{ background: transparent; color: {C['muted']}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {C['gold_hi']}; border-bottom: 2px solid {C['gold']}; }}
QToolTip {{ background: {C['surface2']}; color: {C['text']}; border: 1px solid {C['border']}; padding: 6px;
    border-radius: 6px; }}
QMenu {{ background: {C['surface']}; border: 1px solid {C['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['surface2']}; color: {C['gold_hi']}; }}
#Toast {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 9px; padding: 10px 14px; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "panel"), (QPalette.AlternateBase, "surface"),
                      (QPalette.Button, "surface2"), (QPalette.Text, "text"), (QPalette.WindowText, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "surface2"),
                      (QPalette.ToolTipText, "text"), (QPalette.Highlight, "gold"), (QPalette.PlaceholderText, "faint")):
        pal.setColor(role, QColor(C[key]))
    pal.setColor(QPalette.HighlightedText, QColor("#1a1408"))
    app.setPalette(pal)
    font = QFont("Segoe UI")
    font.setStyleHint(QFont.SansSerif)
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(QSS)
