"""Guard readable visual states and stable geometry in the shared desktop theme."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QVBoxLayout, QWidget

from sqltools.theme import COLORS, apply_theme


def _contrast(foreground, background):
    def luminance(color):
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(channels, (0.2126, 0.7152, 0.0722), strict=True))

    dark, light = sorted((luminance(foreground), luminance(background)))
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize(
    ("foreground", "background", "minimum"),
    [
        ("muted", "input", 4.5),  # Placeholder text, including native macOS controls.
        ("muted", "surface", 4.5),  # Disabled action labels remain legible.
        ("sidebar_muted", "sidebar", 4.5),
        ("accent", "accent_tint", 4.5),
        ("border", "workspace", 3),
        ("success", "workspace", 4.5),
        ("warning", "workspace", 4.5),
        ("error", "workspace", 4.5),
    ],
)
def test_secondary_and_semantic_theme_colors_remain_readable(foreground, background, minimum):
    assert _contrast(COLORS[foreground], COLORS[background]) >= minimum


def test_native_placeholder_and_disabled_labels_use_readable_ink(qtbot):
    apply_theme(QApplication.instance())
    container = QWidget()
    layout = QVBoxLayout(container)
    field = QLineEdit()
    field.setPlaceholderText("Choose an output folder")
    disabled = QCheckBox("Create or use JIRA folder")
    disabled.setEnabled(False)
    layout.addWidget(field)
    layout.addWidget(disabled)
    qtbot.addWidget(container)
    container.show()
    qtbot.wait(10)

    placeholder = field.palette().color(QPalette.ColorRole.PlaceholderText)
    assert placeholder.alpha() == 255
    assert _contrast(placeholder.name(), COLORS["input"]) >= 4.5
    disabled_text = disabled.palette().color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText
    )
    assert _contrast(disabled_text.name(), COLORS["workspace"]) >= 4.5


def test_focus_and_validation_do_not_shift_editable_text(qtbot):
    apply_theme(QApplication.instance())
    container = QWidget()
    layout = QVBoxLayout(container)
    field = QLineEdit("SELECT 1;")
    other = QLineEdit()
    layout.addWidget(field)
    layout.addWidget(other)
    qtbot.addWidget(container)
    container.show()
    other.setFocus()
    qtbot.wait(10)
    initial_cursor = field.inputMethodQuery(Qt.InputMethodQuery.ImCursorRectangle)
    initial_size = field.sizeHint()

    field.setFocus()
    qtbot.wait(10)
    assert field.inputMethodQuery(Qt.InputMethodQuery.ImCursorRectangle) == initial_cursor
    assert field.sizeHint() == initial_size

    field.setProperty("invalid", True)
    field.style().unpolish(field)
    field.style().polish(field)
    qtbot.wait(10)
    assert field.inputMethodQuery(Qt.InputMethodQuery.ImCursorRectangle) == initial_cursor
    assert field.sizeHint() == initial_size
