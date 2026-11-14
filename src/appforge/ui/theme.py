"""Light/dark design tokens and the application stylesheet. Follows the system colour scheme."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Tokens:
    bg: str
    surface: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_soft: str
    danger: str
    danger_soft: str
    ok: str
    dark: bool


LIGHT = Tokens(
    bg="#F2F4F8", surface="#FFFFFF", surface_hover="#F7F9FD", border="#DCE1EA",
    border_strong="#C3CBD9", text="#1B2230", muted="#667088", accent="#2B63D9",
    accent_hover="#2354BC", accent_text="#FFFFFF", accent_soft="#E5EDFD",
    danger="#C93B3B", danger_soft="#FBE9E9", ok="#2E8B57", dark=False,
)
DARK = Tokens(
    bg="#1A1E27", surface="#232936", surface_hover="#29303F", border="#323A4B",
    border_strong="#454F65", text="#E7EAF1", muted="#98A2B6", accent="#6C9CFF",
    accent_hover="#86AEFF", accent_text="#0F1626", accent_soft="#2A3A5E",
    danger="#F07474", danger_soft="#4A2B30", ok="#5CC38A", dark=True,
)

_current = LIGHT


def tokens() -> Tokens:
    return _current


def is_dark(app: QApplication) -> bool:
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    for role, col in (
        (QPalette.Window, t.bg), (QPalette.WindowText, t.text), (QPalette.Base, t.surface),
        (QPalette.AlternateBase, t.surface_hover), (QPalette.Text, t.text),
        (QPalette.Button, t.surface), (QPalette.ButtonText, t.text),
        (QPalette.Highlight, t.accent), (QPalette.HighlightedText, t.accent_text),
        (QPalette.ToolTipBase, t.surface), (QPalette.ToolTipText, t.text),
        (QPalette.PlaceholderText, t.muted), (QPalette.Link, t.accent),
    ):
        p.setColor(role, QColor(col))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(t.muted))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t.muted))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t.muted))
    return p


def stylesheet(t: Tokens) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {t.bg}; }}
    QWidget {{ color: {t.text}; }}
    QLabel {{ background: transparent; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
               padding: 4px 6px; }}

    QLabel#title {{ font-size: 22px; font-weight: 700; }}
    QLabel#subtitle {{ color: {t.muted}; font-size: 12px; }}
    QLabel#sectionLabel {{ color: {t.muted}; font-size: 12px; font-weight: 600; }}
    QLabel#hint {{ color: {t.muted}; font-size: 12px; }}
    QLabel#error {{ color: {t.danger}; font-size: 12px; }}
    QLabel#warning {{ color: {t.muted}; font-size: 12px; }}
    QLabel#emptyTitle {{ font-size: 18px; font-weight: 600; }}
    QLabel#banner {{ background: {t.danger_soft}; color: {t.text}; border: 1px solid {t.danger};
                    border-radius: 8px; padding: 8px 12px; }}

    QLineEdit {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px;
                padding: 7px 10px; selection-background-color: {t.accent}; }}
    QLineEdit:focus {{ border: 1px solid {t.accent}; }}
    QLineEdit:disabled {{ color: {t.muted}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {t.danger}; }}

    QPushButton {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px;
                  padding: 7px 14px; }}
    QPushButton:hover {{ background: {t.surface_hover}; }}
    QPushButton:focus {{ border: 1px solid {t.accent}; }}
    QPushButton:disabled {{ color: {t.muted}; background: transparent; border-color: {t.border}; }}
    QPushButton#primary {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent};
                          font-weight: 600; }}
    QPushButton#primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#primary:disabled {{ background: {t.border}; color: {t.muted}; border-color: {t.border}; }}
    QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {t.accent};
                        padding: 6px 10px; }}
    QPushButton#ghost:hover {{ background: {t.accent_soft}; }}

    QComboBox {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px;
                padding: 6px 28px 6px 10px; min-height: 18px; }}
    QComboBox:focus {{ border: 1px solid {t.accent}; }}
    QComboBox:disabled {{ color: {t.muted}; }}
    QComboBox::drop-down {{ width: 0; border: none; background: transparent; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBoxPrivateContainer {{ background: {t.surface}; border: none; margin: 0; padding: 0; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border_strong};
                                  border-radius: 10px; padding: 4px; outline: none;
                                  selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}
    QComboBox QAbstractItemView::item {{ min-height: 22px; padding: 4px 8px; border-radius: 6px; }}

    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
                  padding: 4px; }}
    QToolButton#gear {{ background: {t.accent}; border: 1px solid {t.accent}; }}
    QToolButton:hover {{ background: {t.accent_soft}; }}
    QToolButton#gear:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QToolButton#gear:focus {{ border: 1px solid {t.accent}; }}
    QToolButton:focus {{ border: 1px solid {t.accent}; }}
    QToolButton::menu-indicator {{ image: none; }}

    QFrame#card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; }}
    QFrame#card[hot="true"] {{ background: {t.surface_hover}; border: 1px solid {t.border_strong}; }}
    QFrame#card[missing="true"] {{ border: 1px dashed {t.danger}; }}
    QLabel#cardName {{ font-size: 15px; font-weight: 650; }}
    QLabel#cardMeta {{ color: {t.muted}; font-size: 12px; }}
    QLabel#cardPath {{ color: {t.muted}; font-size: 11px; }}
    QLabel#chip {{ border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;
                  background: {t.accent_soft}; color: {t.accent}; }}
    QLabel#chip[kind="muted"] {{ background: transparent; color: {t.muted};
                                border: 1px solid {t.border}; }}
    QLabel#chip[kind="danger"] {{ background: {t.danger_soft}; color: {t.danger}; }}
    QLabel#chip[kind="ok"] {{ background: transparent; color: {t.ok}; border: 1px solid {t.ok}; }}
    QLabel#chip[kind="update"] {{ background: {t.accent}; color: {t.accent_text}; }}
    QPushButton#soft {{ background: {t.accent_soft}; color: {t.accent}; border: 1px solid transparent;
                       font-weight: 600; }}
    QPushButton#soft:hover {{ border: 1px solid {t.accent}; }}
    QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    QListWidget {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px; padding: 4px; }}
    QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
    QListWidget#discoveryRoots {{ outline: none; }}
    QListWidget#discoveryRoots::item {{ padding: 4px 10px; }}

    QLabel#iconTile {{ background: {t.bg}; border-radius: 14px; }}
    QLabel#previewTile {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 18px; }}

    QMenu {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 10px;
            padding: 6px; }}
    QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
    QMenu::item:disabled {{ color: {t.muted}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 5px 6px; }}

    QStatusBar {{ background: transparent; color: {t.muted}; }}
    QStatusBar::item {{ border: none; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QCheckBox {{ spacing: 8px; }}
    QMessageBox {{ background: {t.bg}; }}
    """


def apply_theme(app: QApplication) -> Tokens:
    global _current
    _current = DARK if is_dark(app) else LIGHT
    app.setStyle("Fusion")
    app.setPalette(_palette(_current))
    app.setStyleSheet(stylesheet(_current))
    return _current
