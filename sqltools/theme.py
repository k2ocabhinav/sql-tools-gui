"""SQL Tools visual tokens and platform-native type defaults."""

import tempfile
import zlib
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication

COLORS = {
    "sidebar": "#353945",
    "sidebar_text": "#F3F4F6",
    "sidebar_muted": "#C8CCD3",
    "sidebar_hover": "#494F5E",
    "workspace": "#D9DDE5",
    "surface": "#E4E8EE",
    "input": "#F1F3F7",
    "text": "#202431",
    "muted": "#4D5665",
    "border": "#707B8C",
    "divider": "#B6BECA",
    "scroll": "#9AA3B2",
    "accent": "#623A96",
    "accent_hover": "#563283",
    "accent_pressed": "#482A6D",
    "accent_tint": "#E8E0F2",
    "accent_disabled": "#B7A9CC",
    "success": "#285A3A",
    "success_bg": "#DDE8DF",
    "warning": "#70500C",
    "warning_bg": "#EEE5D2",
    "error": "#81353C",
    "error_bg": "#EEDFE1",
    "diff_a": "#EEDFE1",
    "diff_b": "#DDE8DF",
    "diff_changed": "#EEE5D2",
}


def _ui_font() -> QFont:
    general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    # Keep the OS-provided size and family by default.  Point sizes scale
    # correctly on each platform and when a user changes display scaling.
    if general.pointSizeF() <= 0:
        general.setPointSizeF(10.5)
    return general


def _draw_icon(path: Path, size: int, scale: int, points, color: str, width: float) -> None:
    """Paint a small stroke icon at 1x/2x so stylesheet-drawn controls stay crisp."""
    image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), width * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(x * scale, y * scale) for x, y in points])
    painter.end()
    image.save(str(path))


def _control_icons() -> Path:
    """Write the few glyphs Qt stylesheets cannot draw themselves (check, chevrons).

    They are generated with QPainter rather than shipped so the package carries no
    image assets and the glyphs always follow the theme tokens. The folder name
    carries a hash of the glyph definitions, so a changed design never reuses stale
    files, and existing files are left alone, so two running instances cannot
    overwrite each other mid-read. If the temp folder is not writable the app still
    starts; the controls just lose their glyphs.
    """
    glyphs = {
        "check": (16, ((4, 8.5), (7, 11.5), (12, 5)), "#FFFFFF", 2.0),
        "chevron-up": (12, ((2.5, 7.5), (6, 4), (9.5, 7.5)), COLORS["text"], 1.6),
        "chevron-down": (12, ((2.5, 4.5), (6, 8), (9.5, 4.5)), COLORS["text"], 1.6),
    }
    digest = f"{zlib.crc32(repr(glyphs).encode()):08x}"
    folder = Path(tempfile.gettempdir()) / f"sqltools-theme-icons-{digest}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, (size, points, color, width) in glyphs.items():
            for scale, suffix in ((1, ""), (2, "@2x")):
                target = folder / f"{name}{suffix}.png"
                if not target.exists():
                    _draw_icon(target, size, scale, points, color, width)
    except OSError:
        pass
    return folder


def _icon_url(folder: Path, name: str) -> str:
    return f'url("{(folder / f"{name}.png").as_posix()}")'


def apply_theme(app: QApplication) -> None:
    icons = _control_icons()
    app.setFont(_ui_font())
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["workspace"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["input"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS["muted"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(COLORS["accent"]))
    # Native disabled text must remain readable on every platform. In particular,
    # do not inherit a host dark-mode palette for these explicitly light surfaces.
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QWidget {{ color: {COLORS['text']}; }}
        QMainWindow, QWidget#workspace {{ background: {COLORS['workspace']}; }}
        QWidget#sidebar {{ background: {COLORS['sidebar']}; border-radius: 9px; }}
        QLabel#brand {{ color: {COLORS['sidebar_text']}; font-size: 15pt; font-weight: 600; }}
        QLabel#versionLabel {{ color: {COLORS['sidebar_muted']}; }}
        QToolButton#navItem {{ color: {COLORS['sidebar_text']}; border: 1px solid transparent;
            border-radius: 6px; padding: 8px 10px; text-align: left; }}
        QToolButton#navItem:hover {{ background: {COLORS['sidebar_hover']}; }}
        QToolButton#navItem:checked {{ color: #FFFFFF; background: {COLORS['accent']};
            font-weight: 600; }}
        QToolButton#navItem:focus {{ border-color: {COLORS['sidebar_text']}; }}
        QLabel#pageTitle {{ font-size: 18pt; font-weight: 600; }}
        QLabel#sectionTitle {{ font-weight: 600; }}
        QLabel#muted, QLabel#sidebarSubtitle {{ color: {COLORS['muted']}; }}
        QWidget#sidebar QLabel#versionLabel {{ color: {COLORS['sidebar_muted']}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableView, QListView {{
            background: {COLORS['input']}; border: 1px solid {COLORS['border']};
            placeholder-text-color: {COLORS['muted']};
            border-radius: 6px; padding: 5px 7px;
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus,
        QTableView:focus, QListView:focus {{ border-color: {COLORS['accent']}; }}
        QLineEdit[invalid="true"], QComboBox[invalid="true"] {{
            border-color: {COLORS['error']}; }}
        QPushButton {{ border: 1px solid {COLORS['border']}; border-radius: 6px;
            background: {COLORS['surface']}; padding: 6px 11px; min-height: 20px; }}
        QPushButton:hover {{ background: {COLORS['accent_tint']}; }}
        QPushButton:pressed {{ background: {COLORS['divider']}; }}
        QPushButton#primary {{ color: #FFFFFF; background: {COLORS['accent']};
            border-color: {COLORS['accent']}; font-weight: 600; }}
        QPushButton#primary:hover {{ background: {COLORS['accent_hover']}; }}
        QPushButton#primary:pressed {{ background: {COLORS['accent_pressed']}; }}
        QPushButton:disabled {{ color: {COLORS['muted']}; background: {COLORS['surface']}; }}
        QPushButton#primary:disabled {{ color: {COLORS['muted']};
            background: {COLORS['surface']}; border-color: {COLORS['divider']}; }}
        QPushButton#segment {{ background: transparent; border-color: transparent;
            padding: 5px 9px; }}
        QPushButton#segment:hover {{ background: {COLORS['surface']}; }}
        QPushButton#segment:checked {{ color: {COLORS['accent']};
            background: {COLORS['accent_tint']}; border-color: {COLORS['accent_tint']};
            font-weight: 600; }}
        QPushButton:focus, QPushButton#segment:focus {{ border-color: {COLORS['accent']}; }}
        QPushButton#primary:focus {{ border-color: {COLORS['input']}; }}
        QWidget#choiceSwitch {{ background: {COLORS['workspace']}; border-radius: 7px; }}
        QCheckBox:disabled {{ color: {COLORS['muted']}; }}
        QCheckBox {{ spacing: 8px; padding: 3px 0; }}
        QCheckBox::indicator, QAbstractItemView::indicator {{ width: 16px; height: 16px;
            border: 1px solid {COLORS['border']}; border-radius: 4px;
            background: {COLORS['input']}; }}
        QCheckBox::indicator:hover {{ border-color: {COLORS['accent']}; }}
        QCheckBox::indicator:focus {{ border-color: {COLORS['accent']}; }}
        QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
            background: {COLORS['accent']}; border-color: {COLORS['accent']};
            image: {_icon_url(icons, 'check')}; }}
        QCheckBox::indicator:disabled {{ background: {COLORS['surface']};
            border-color: {COLORS['divider']}; }}
        QCheckBox::indicator:checked:disabled {{ background: {COLORS['accent_disabled']};
            border-color: {COLORS['accent_disabled']}; }}
        QComboBox {{ padding-right: 28px; }}
        QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
            width: 24px; border: none; }}
        QComboBox::down-arrow {{ image: {_icon_url(icons, 'chevron-down')};
            width: 12px; height: 12px; }}
        QSpinBox {{ padding-right: 26px; }}
        QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border;
            width: 22px; background: {COLORS['surface']};
            border-left: 1px solid {COLORS['divider']}; }}
        QSpinBox::up-button {{ subcontrol-position: top right;
            border-top-right-radius: 5px; border-bottom: 1px solid {COLORS['divider']}; }}
        QSpinBox::down-button {{ subcontrol-position: bottom right;
            border-bottom-right-radius: 5px; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background: {COLORS['accent_tint']}; }}
        QSpinBox::up-arrow {{ image: {_icon_url(icons, 'chevron-up')};
            width: 10px; height: 10px; }}
        QSpinBox::down-arrow {{ image: {_icon_url(icons, 'chevron-down')};
            width: 10px; height: 10px; }}
        QToolButton#disclosure {{ color: {COLORS['muted']}; border: 1px solid transparent;
            border-radius: 5px; padding: 5px 7px; text-align: left; }}
        QToolButton#disclosure:hover {{ background: {COLORS['surface']}; }}
        QToolButton#disclosure:focus {{ border-color: {COLORS['accent']}; }}
        QScrollBar:vertical {{ background: transparent; width: 14px; margin: 2px 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 14px; margin: 0 2px; }}
        QScrollBar::handle:vertical {{ background: {COLORS['scroll']}; border-radius: 4px;
            min-height: 28px; margin: 0 1px 0 5px; }}
        QScrollBar::handle:horizontal {{ background: {COLORS['scroll']}; border-radius: 4px;
            min-width: 28px; margin: 5px 0 1px 0; }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {COLORS['border']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0; height: 0; border: none; background: transparent;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        QHeaderView::section {{ color: {COLORS['text']}; background: {COLORS['surface']};
            border: none; border-bottom: 1px solid {COLORS['divider']}; padding: 5px 7px; }}
        QTableCornerButton::section {{ background: {COLORS['surface']};
            border: none; border-bottom: 1px solid {COLORS['divider']}; }}
        QTableView {{ alternate-background-color: {COLORS['surface']};
            gridline-color: {COLORS['divider']}; selection-background-color: {COLORS['accent']};
            selection-color: #FFFFFF; }}
        QTabWidget::pane {{ border: 1px solid {COLORS['divider']}; border-radius: 5px; }}
        QTabBar::tab {{ color: {COLORS['muted']}; background: transparent;
            border: none; padding: 5px 10px; }}
        QTabBar::tab:selected {{ color: {COLORS['accent']}; font-weight: 600;
            border-bottom: 2px solid {COLORS['accent']}; }}
        QProgressBar {{ border: none; border-radius: 2px; background: {COLORS['divider']};
            text-align: center; max-height: 4px; }}
        QProgressBar::chunk {{ background: {COLORS['accent']}; border-radius: 2px; }}
        QSplitter::handle {{ background: transparent; }}
        QLabel#status[status="success"] {{ color: {COLORS['success']}; }}
        QLabel#status[status="partial"] {{ color: {COLORS['warning']}; }}
        QLabel#status[status="failed"] {{ color: {COLORS['error']}; }}
        QLabel#status[status="cancelled"] {{ color: {COLORS['muted']}; }}
        QLabel#fieldError {{ color: {COLORS['error']}; font-size: 9pt; }}
        """
    )
