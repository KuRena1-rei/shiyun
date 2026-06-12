COLORS = {
    "mint": "#4CAF8B",
    "mint_dark": "#3D9B7A",
    "mint_light": "#E8F5E9",
    "mint_hover": "#C8E6C9",
    "bg": "#FFFFFF",
    "sidebar_bg": "#F7FAF8",
    "card_bg": "#FFFFFF",
    "card_hover": "#F1F8F3",
    "border": "#E0E8E4",
    "text": "#2E3A3A",
    "text_sec": "#6B7B7B",
    "text_hint": "#A0B0B0",
    "danger": "#E57373",
    "danger_bg": "#FFEBEE",
    "warning": "#FF9800",
    "question": "#2196F3",
    "white": "#FFFFFF",
}


def get_stylesheet() -> str:
    return f"""
    QWidget {{
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 13px;
        color: {COLORS['text']};
        background-color: {COLORS['bg']};
    }}

    /* Sidebar */
    QWidget#sidebar {{
        background-color: {COLORS['sidebar_bg']};
        border-right: 1px solid {COLORS['border']};
    }}

    /* Scroll areas */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS['border']};
        border-radius: 3px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLORS['mint']};
    }}
    QScrollBar::add-line, QScrollBar::sub-line,
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
        height: 0px;
    }}

    /* Connection card */
    QWidget#connCard {{
        background-color: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
    }}
    QWidget#connCard:hover {{
        background-color: {COLORS['card_hover']};
    }}
    QWidget#connCard[active="true"] {{
        background-color: {COLORS['mint_light']};
        border: 1px solid {COLORS['mint']};
    }}

    /* Main window */
    QWidget#centralWidget {{
        background-color: transparent;
    }}

    /* File row */
    QWidget#fileRow {{
        background-color: {COLORS['bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
    }}
    QWidget#fileRow:hover {{
        background-color: {COLORS['card_hover']};
    }}

    /* Buttons */
    QPushButton {{
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton#newConnBtn {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        background: transparent;
        color: {COLORS['text']};
        font-weight: bold;
        padding: 8px;
    }}
    QPushButton#newConnBtn:hover {{
        background-color: {COLORS['card_hover']};
    }}
    QPushButton#uploadBtn {{
        background-color: {COLORS['mint']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton#uploadBtn:hover {{
        background-color: {COLORS['mint_dark']};
    }}
    QPushButton#refreshBtn {{
        border: 1px solid {COLORS['border']};
        background: transparent;
        color: {COLORS['text']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton#refreshBtn:hover {{
        background-color: {COLORS['card_hover']};
    }}
    QPushButton#disconnectBtn {{
        border: 1px solid {COLORS['danger']};
        background: transparent;
        color: {COLORS['danger']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton#disconnectBtn:hover {{
        background-color: {COLORS['danger_bg']};
    }}
    QPushButton#deleteBtn {{
        background: transparent;
        border: none;
        color: {COLORS['danger']};
        font-size: 16px;
    }}
    QPushButton#deleteBtn:hover {{
        background-color: {COLORS['danger_bg']};
        border-radius: 10px;
    }}

    /* Line edits */
    QLineEdit {{
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 6px 10px;
        background: {COLORS['bg']};
    }}
    QLineEdit:focus {{
        border-color: {COLORS['mint']};
    }}

    /* Title bar */
    QWidget#titleBar {{
        background-color: {COLORS['sidebar_bg']};
        border-bottom: 1px solid {COLORS['border']};
    }}
    QPushButton#minBtn, QPushButton#maxBtn {{
        background: transparent;
        border: none;
        color: {COLORS['text_sec']};
        font-size: 14px;
        border-radius: 0px;
        padding: 0px;
    }}
    QPushButton#minBtn:hover, QPushButton#maxBtn:hover {{
        background-color: {COLORS['mint_light']};
        color: {COLORS['text']};
    }}
    QPushButton#closeTitleBarBtn {{
        background: transparent;
        border: none;
        color: {COLORS['text_sec']};
        font-size: 16px;
        border-radius: 0px;
        padding: 0px;
    }}
    QPushButton#closeTitleBarBtn:hover {{
        background-color: {COLORS['danger']};
        color: white;
    }}

    /* Dialog */
    QDialog {{
        background-color: {COLORS['bg']};
    }}
    QWidget#connDialogContent {{
        background-color: {COLORS['bg']};
    }}
    """


def setup_theme(app: "QApplication") -> None:
    app.setStyleSheet(get_stylesheet())


def make_confirm_button(text: str, parent: "QWidget | None" = None) -> "QPushButton":
    from PySide6.QtWidgets import QPushButton
    btn = QPushButton(text, parent)
    btn.setFixedSize(80, 32)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {COLORS['mint']}; color: white; border: none; border-radius: 4px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {COLORS['mint_dark']}; }}"
    )
    return btn


def make_cancel_button(text: str, parent: "QWidget | None" = None) -> "QPushButton":
    from PySide6.QtWidgets import QPushButton
    btn = QPushButton(text, parent)
    btn.setFixedSize(80, 32)
    btn.setStyleSheet(
        f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; color: {COLORS['text']}; border-radius: 4px; }}"
        f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
    )
    return btn


def make_danger_button(text: str, parent: "QWidget | None" = None) -> "QPushButton":
    from PySide6.QtWidgets import QPushButton
    btn = QPushButton(text, parent)
    btn.setFixedSize(80, 32)
    btn.setStyleSheet(
        f"QPushButton {{ border: 1px solid {COLORS['danger']}; background: transparent; color: {COLORS['danger']}; border-radius: 4px; }}"
        f"QPushButton:hover {{ background-color: {COLORS['danger_bg']}; }}"
    )
    return btn


def menu_stylesheet(extra_items: str = "") -> str:
    base = f"""
        QMenu {{
            background-color: {COLORS['bg']};
            border: 1px solid {COLORS['border']};
            border-radius: 6px;
            padding: 4px 0px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 16px;
            color: {COLORS['text']};
        }}
        QMenu::item:selected {{
            background-color: {COLORS['mint_light']};
            color: {COLORS['text']};
        }}
    """
    return base + extra_items
