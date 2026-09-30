from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class CheckBox(QCheckBox):
    """Checkbox whose layout rect is its widget rect.

    Native macOS reports a smaller layout rect for check boxes, which insets every
    sibling field in the same layout by a couple of pixels.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)


class _CurrentPageStack(QStackedWidget):
    """A stack whose requested height follows the visible input mode."""

    def sizeHint(self):
        current = self.currentWidget()
        if current is None:
            return super().sizeHint()
        hint = current.sizeHint()
        minimum_hint = current.minimumSizeHint()
        minimum = current.minimumSize()
        return QSize(
            max(hint.width(), minimum_hint.width(), minimum.width()),
            max(hint.height(), minimum_hint.height(), minimum.height()),
        )

    def minimumSizeHint(self):
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()
        hint = current.minimumSizeHint()
        minimum = current.minimumSize()
        return QSize(
            max(hint.width(), minimum.width()),
            max(hint.height(), minimum.height()),
        )


class ChoiceSwitch(QWidget):
    """Compact keyboard-operable segmented source selector."""

    currentIndexChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("choiceSwitch")
        self.setAccessibleName("Source input method")
        self.setAccessibleDescription("Use the left and right arrow keys to change input method.")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._items: list[tuple[str, object]] = []
        self._current_index = -1
        self._buttons = QButtonGroup(self)
        self._buttons.setExclusive(True)
        self._buttons.idToggled.connect(self._checked_changed)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(2)

    def addItem(self, text: str, data: object) -> None:
        index = len(self._items)
        self._items.append((text, data))
        button = QPushButton(text, self)
        button.setObjectName("segment")
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAccessibleName(text)
        # The checked segment is semibold; reserve its wider text so selection
        # never clips a label or shifts its neighbours.
        bold = QFont(button.font())
        bold.setWeight(QFont.Weight.DemiBold)
        button.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 22)
        self._buttons.addButton(button, index)
        self._layout.addWidget(button)
        if index == 0:
            self._current_index = 0
            button.setChecked(True)

    def currentData(self) -> object | None:
        return (
            self._items[self._current_index][1]
            if 0 <= self._current_index < len(self._items)
            else None
        )

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._buttons.button(index).setChecked(True)

    def _checked_changed(self, index: int, checked: bool) -> None:
        # Native accessibility actions can change the checked state without
        # emitting clicked. Keep the displayed selection and source data in sync.
        if checked:
            self._select(index)

    def _select(self, index: int) -> None:
        if index == self._current_index:
            return
        self._current_index = index
        self.currentIndexChanged.emit(index)

    def keyPressEvent(self, event) -> None:
        if self._items and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -1 if event.key() == Qt.Key.Key_Left else 1
            self.setCurrentIndex((self._current_index + delta) % len(self._items))
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)


class SourceModePanel(QWidget):
    """Keep source selection and its active input aligned in one expanding panel."""

    currentIndexChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sourceModePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.switch = ChoiceSwitch(self)
        self.switch.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.content = _CurrentPageStack(self)
        self.content.setObjectName("sourceModeContent")
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.content)
        self.switch.currentIndexChanged.connect(self._select_mode)

    def addMode(self, label: str, value: object, widget: QWidget) -> None:
        # Give every source type the same top-left anchor. Expanding inputs such
        # as SQL editors take the available height; fixed-height rows (folder
        # and file pickers) stay at the top instead of drifting through a tall
        # source column. Keeping this rule here prevents page-specific spacing
        # regressions when another input mode is added.
        content = QWidget(self.content)
        content.setObjectName("sourceModeSlot")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(widget, 1)
        self.switch.addItem(label, value)
        self.content.addWidget(content)

    def currentData(self) -> object | None:
        return self.switch.currentData()

    def currentIndex(self) -> int:
        return self.switch.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.switch.setCurrentIndex(index)

    def _select_mode(self, index: int) -> None:
        self.content.setCurrentIndex(index)
        self.content.updateGeometry()
        self.updateGeometry()
        parent_layout = self.parentWidget().layout() if self.parentWidget() else None
        if parent_layout is not None:
            parent_layout.invalidate()
        self.currentIndexChanged.emit(index)


class MultiFilePicker(QWidget):
    """Readable multi-file selection with full paths kept out of the main display."""

    pathsChanged = Signal()

    def __init__(self, parent: QWidget, title: str = "Select SQL files"):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._dialog_parent = parent
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self.list = QListWidget()
        self.list.setAccessibleName("Selected files")
        self.control = self.list
        self.list.setMinimumHeight(68)
        self.list.setMaximumHeight(106)
        layout.addWidget(self.list)
        self.error_label = QLabel()
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.list.itemSelectionChanged.connect(
            lambda: self.remove_button.setEnabled(bool(self.list.selectedItems()))
        )
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        self.count = QLabel("No files selected")
        self.count.setObjectName("muted")
        # Let the status text give way before the buttons do, so a narrow column
        # never gets wider (and scrolls sideways) just to fit this caption.
        self.count.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.add_button = QPushButton("Add files…")
        self.remove_button = QPushButton("Remove selected")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self.add_files)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear)
        actions.addWidget(self.count, 1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        layout.addLayout(actions)
        self._update_count()

    def paths(self) -> list[str]:
        return [
            self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())
        ]

    def add_paths(self, paths: list[str]) -> None:
        known = set(self.paths())
        for path in paths:
            if path in known:
                continue
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
            known.add(path)
        self._update_count()
        self.pathsChanged.emit()

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self._dialog_parent, self._title, "", "SQL files (*.sql);;All files (*)"
        )
        self.add_paths(paths)

    def remove_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._update_count()
        self.pathsChanged.emit()

    def clear(self) -> None:
        self.list.clear()
        self._update_count()
        self.pathsChanged.emit()

    def _update_count(self) -> None:
        count = self.list.count()
        self.count.setText(
            f"{count} file{'s' if count != 1 else ''} selected" if count else "No files selected"
        )
        self.remove_button.setEnabled(bool(self.list.selectedItems()))
        self.clear_button.setEnabled(bool(count))


def source_file_picker_panel(parent: QWidget, title: str) -> tuple[QWidget, MultiFilePicker]:
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    label = QLabel("Selected SQL files")
    label.setObjectName("fieldLabel")
    layout.addWidget(label)
    picker = MultiFilePicker(parent, title)
    layout.addWidget(picker)
    return panel, picker


def page_heading(title: str, description: str) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 12)
    layout.setSpacing(3)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    detail = QLabel(description)
    detail.setObjectName("muted")
    detail.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(detail)
    return box


def sql_editor(placeholder: str, minimum_height: int = 140) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setPlaceholderText(placeholder)
    editor.setAccessibleName("SQL source")
    editor.setMinimumHeight(minimum_height)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    editor.setFont(fixed)
    return editor


def path_row(
    parent: QWidget,
    label_text: str,
    *,
    directory: bool = True,
    key: str = "path",
    save_file: bool = False,
    initial: str = "",
) -> tuple[QWidget, QLineEdit]:
    row = QWidget()
    outer = QVBoxLayout(row)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(5)
    label = QLabel(label_text)
    label.setObjectName("fieldLabel")
    outer.addWidget(label)
    controls = QWidget()
    layout = QHBoxLayout(controls)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    edit = QLineEdit()
    edit.setObjectName(key)
    edit.setAccessibleName(label_text)
    label.setBuddy(edit)
    edit.setClearButtonEnabled(True)
    edit.setPlaceholderText("Choose a folder" if directory else "Choose files")
    edit.setText(initial)
    button = QPushButton("Browse…")
    button.setAccessibleName(f"Browse {label_text.lower()}")

    def browse() -> None:
        current = edit.text().strip()
        start = current if Path(current).exists() else ""
        if directory:
            selected = QFileDialog.getExistingDirectory(parent, label_text, start)
        elif save_file:
            selected, _ = QFileDialog.getSaveFileName(parent, label_text, start)
        else:
            selected, _ = QFileDialog.getOpenFileNames(parent, label_text, start)
            selected = "; ".join(selected)
        if selected:
            edit.setText(selected)

    button.clicked.connect(browse)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    outer.addWidget(controls)
    row.error_label = QLabel()
    row.error_label.setObjectName("fieldError")
    row.error_label.setWordWrap(True)
    row.error_label.hide()
    outer.addWidget(row.error_label)
    row.control = edit
    row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    edit.validation_field = row
    return row, edit


def labeled_field(label_text: str, control: QWidget, *, helper: str = "") -> QWidget:
    field = QWidget()
    layout = QVBoxLayout(field)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    label = QLabel(label_text)
    label.setObjectName("fieldLabel")
    label.setBuddy(control)
    if not control.accessibleName():
        control.setAccessibleName(label_text)
    layout.addWidget(label)
    layout.addWidget(control)
    if helper:
        hint = QLabel(helper)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
    error = QLabel()
    error.setObjectName("fieldError")
    error.setWordWrap(True)
    error.hide()
    layout.addWidget(error)
    field.error_label = error
    field.control = control
    control.validation_field = field
    return field


class StackedFormLayout(QVBoxLayout):
    """Small form helper that aligns settings with labels above their fields."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(9)

    def addRow(self, label: str, control: QWidget) -> None:
        if label:
            self.addWidget(labeled_field(label, control))
        else:
            self.addWidget(control)


def form_layout(parent: QWidget | QVBoxLayout) -> StackedFormLayout:
    layout = StackedFormLayout()
    if isinstance(parent, QWidget):
        parent.setLayout(layout)
    else:
        parent.addLayout(layout)
    return layout


def run_button(text: str = "Run") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("primary")
    button.setMinimumWidth(132)
    return button


def readonly_summary(parent: QWidget, height: int = 100) -> QPlainTextEdit:
    box = QPlainTextEdit(parent)
    box.setReadOnly(True)
    box.setMaximumHeight(height)
    box.setPlaceholderText("Results and diagnostics appear here.")
    return box


def selected_file_paths(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def add_labeled_row(layout: QVBoxLayout, widget: QWidget, label: str) -> None:
    layout.addWidget(labeled_field(label, widget))
