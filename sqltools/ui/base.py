from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sqltools.services import FeatureOutcome
from sqltools.ui.widgets import SourceModePanel, page_heading, readonly_summary


class ResponsiveColumns(QWidget):
    """Two tool sections that flow into one compact column on narrow windows."""

    BREAKPOINT = 760

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("responsiveColumns")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.panels: list[QWidget] = []
        self.panel_layouts: list[QVBoxLayout] = []
        for _ in range(2):
            panel = QWidget(self)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)
            self.panels.append(panel)
            self.panel_layouts.append(layout)
        self.tail = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self._horizontal: bool | None = None
        self.set_horizontal(False)

    def finish_inputs(self) -> None:
        for layout in self.panel_layouts:
            layout.addStretch(1)

    def set_horizontal(self, horizontal: bool) -> None:
        if self._horizontal == horizontal:
            return
        self._horizontal = horizontal
        for panel in self.panels:
            self.grid.removeWidget(panel)
        self.grid.removeItem(self.tail)
        for index in range(3):
            self.grid.setRowStretch(index, 0)
        for index in range(2):
            self.grid.setColumnStretch(index, 0)
        if horizontal:
            self.grid.addWidget(self.panels[0], 0, 0)
            self.grid.addWidget(self.panels[1], 0, 1)
            self.grid.addItem(self.tail, 1, 0, 1, 2)
            self.grid.setColumnStretch(0, 2)
            self.grid.setColumnStretch(1, 1)
            self.grid.setRowStretch(1, 1)
        else:
            self.grid.addWidget(self.panels[0], 0, 0)
            self.grid.addWidget(self.panels[1], 1, 0)
            self.grid.addItem(self.tail, 2, 0)
            self.grid.setColumnStretch(0, 1)
            self.grid.setRowStretch(2, 1)

    def available_width(self) -> int:
        """Width the columns can really use: the enclosing scroll viewport.

        The widget's own width is no help here: inside a scroll area it grows to its
        minimum size, so a layout that does not fit would always look like it fits.
        """
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent.viewport().width()
            parent = parent.parentWidget()
        return self.width()

    def fits_side_by_side(self) -> bool:
        """Side by side only when both columns fit at their minimum widths.

        Text width depends on the platform, display scaling and the user's text size,
        so a fixed breakpoint alone would let wider fonts push the page sideways.
        """
        available = self.available_width()
        if available < self.BREAKPOINT:
            return False
        needed = sum(panel.minimumSizeHint().width() for panel in self.panels)
        return needed + self.grid.horizontalSpacing() <= available

    def refresh(self) -> None:
        self.set_horizontal(self.fits_side_by_side())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh()

    def event(self, event) -> bool:
        handled = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest:
            # A child's minimum size changed (for example a different input mode).
            self.refresh()
        return handled


class FeaturePage(QWidget):
    """Shared page heading, responsive input area, action footer, and diagnostics."""

    request_job = Signal(str, object, object)
    clear_shell_status_requested = Signal()

    def __init__(self, title: str, description: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._run_buttons: list[QPushButton] = []
        self._validation_messages: dict[QWidget, str] = {}
        self._reduce_motion = False
        self._feedback_height = 148
        self._responsive_columns: list[ResponsiveColumns] = []

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(24, 18, 24, 16)
        self.outer.setSpacing(10)
        self.outer.addWidget(page_heading(title, description))

        self.content_widget = QWidget()
        self.input_layout = QVBoxLayout(self.content_widget)
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_layout.setSpacing(16)
        self.input_scroll: QScrollArea | None = QScrollArea()
        self.input_scroll.setWidgetResizable(True)
        self.input_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.input_scroll.setWidget(self.content_widget)
        self.outer.addWidget(self.input_scroll, 1)

        self.actions_row = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_row)
        self.actions_layout.setContentsMargins(0, 3, 0, 0)
        self.actions_layout.setSpacing(8)
        self.outer.addWidget(self.actions_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.outer.addWidget(self.progress)

        self.footer_row = QWidget()
        footer_layout = QHBoxLayout(self.footer_row)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setProperty("status", "")
        self.status.setMinimumHeight(24)
        # Long paths in errors wrap instead of widening the page (and window).
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer_layout.addWidget(self.status, 1)
        self.feedback_toggle = QToolButton()
        self.feedback_toggle.setObjectName("disclosure")
        self.feedback_toggle.setText("Activity")
        self.feedback_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.feedback_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.feedback_toggle.setCheckable(True)
        self.feedback_toggle.setChecked(False)
        self.feedback_toggle.setAccessibleName("Show activity and diagnostics")
        self.feedback_toggle.toggled.connect(self._set_feedback_open)
        footer_layout.addWidget(self.feedback_toggle)
        self.outer.addWidget(self.footer_row)

        self.feedback_panel = QTabWidget()
        self.summary = readonly_summary(self.feedback_panel, 118)
        self.summary.setPlaceholderText("Operation summaries appear here.")
        self.diagnostics = readonly_summary(self.feedback_panel, 118)
        self.diagnostics.setPlaceholderText("Warnings and errors appear here.")
        self.feedback_panel.addTab(self.summary, "Activity")
        self.feedback_panel.addTab(self.diagnostics, "Diagnostics")
        self.feedback_panel.setMaximumHeight(0)
        self.feedback_panel.setVisible(False)
        self.outer.addWidget(self.feedback_panel)

        self._feedback_animation = QPropertyAnimation(self.feedback_panel, b"maximumHeight", self)
        self._feedback_animation.setDuration(120)
        self._feedback_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._feedback_animation.finished.connect(self._feedback_animation_finished)

    def add_group(
        self,
        title: str,
        target_layout=None,
        *,
        row: int | None = None,
        column: int = 0,
        row_span: int = 1,
        column_span: int = 1,
    ) -> tuple[QWidget, QVBoxLayout]:
        section = QWidget()
        section.setObjectName("section")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(heading)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        layout.addLayout(content)
        target = self.input_layout if target_layout is None else target_layout
        if isinstance(target, QGridLayout) and row is not None:
            target.addWidget(section, row, column, row_span, column_span)
        else:
            target.addWidget(section)
        return section, content

    def add_two_column_layout(self) -> tuple[QVBoxLayout, QVBoxLayout]:
        columns = ResponsiveColumns(self.content_widget)
        self._responsive_columns.append(columns)
        self.input_layout.addWidget(columns, 1)
        return columns.panel_layouts[0], columns.panel_layouts[1]

    def set_workspace_widget(self, widget: QWidget) -> None:
        if self.input_scroll is None:
            return
        index = self.outer.indexOf(self.input_scroll)
        self.outer.removeWidget(self.input_scroll)
        self.outer.insertWidget(index, widget, 1)
        self.input_scroll.setParent(None)
        self.input_scroll.deleteLater()
        self.input_scroll = None

    def add_actions(self, *buttons: QPushButton) -> None:
        clears = [button for button in buttons if button.text().startswith("Clear")]
        remaining = [button for button in buttons if button not in clears]
        for button in clears:
            self.actions_layout.addWidget(button)
        self.actions_layout.addStretch(1)
        for button in remaining:
            if button.objectName() != "primary":
                self.actions_layout.addWidget(button)
        for button in remaining:
            if button.objectName() == "primary":
                self.actions_layout.addWidget(button)
            self._run_buttons.append(button)
        self._run_buttons.extend(clears)

    def finish_inputs(self) -> None:
        """Keep responsive sections top-aligned while their container grows."""
        for columns in self._responsive_columns:
            columns.finish_inputs()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # The scroll viewport can change size without its content widget changing.
        for columns in self._responsive_columns:
            columns.refresh()

    def set_busy(self, busy: bool) -> None:
        for button in self._run_buttons:
            button.setEnabled(not busy)

    def set_reduce_motion(self, enabled: bool) -> None:
        self._reduce_motion = enabled
        if enabled:
            self._feedback_animation.stop()
            opened = self.feedback_toggle.isChecked()
            self.feedback_panel.setVisible(opened)
            self.feedback_panel.setMaximumHeight(self._feedback_height if opened else 0)

    def show_progress(self, message: str, value: int) -> None:
        self._set_status(message, "")
        if value < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(value)
        self.progress.show()

    def _set_status(self, message: str, status: str | None = None) -> None:
        self.status.setText(message)
        self.status.setToolTip(message if len(message) > 90 else "")
        if not message:
            self.clear_shell_status_requested.emit()
        if status is not None:
            self.status.setProperty("status", status)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    def set_field_error(self, control: QWidget, message: str) -> None:
        self._validation_messages[control] = message
        field = getattr(control, "validation_field", control)
        target = getattr(field, "control", field)
        target.setProperty("invalid", True)
        target.style().unpolish(target)
        target.style().polish(target)
        label = getattr(field, "error_label", None)
        if label is not None:
            label.setText(message)
            label.show()
        self._set_status(message, "failed")
        if not getattr(control, "_validation_connected", False):
            signal = getattr(control, "textChanged", None) or getattr(control, "pathsChanged", None)
            if signal is not None:
                signal.connect(lambda *_: self.clear_field_error(control))
                control._validation_connected = True
            # An error for an inactive source mode is no longer actionable.
            # Clear its presentation when switching, while preserving input data.
            ancestor = control.parentWidget()
            while ancestor is not None:
                if isinstance(ancestor, SourceModePanel):
                    ancestor.currentIndexChanged.connect(
                        lambda *_: self.clear_field_error(control)
                    )
                    control._validation_connected = True
                    break
                ancestor = ancestor.parentWidget()
        target.setFocus()

    def clear_field_error(self, control: QWidget) -> None:
        message = self._validation_messages.pop(control, None)
        field = getattr(control, "validation_field", control)
        target = getattr(field, "control", field)
        if target.property("invalid"):
            target.setProperty("invalid", False)
            target.style().unpolish(target)
            target.style().polish(target)
        label = getattr(field, "error_label", None)
        if label is not None:
            label.clear()
            label.hide()
        if self.status.property("status") == "failed" and self.status.text() == message:
            self._set_status("", "")

    def set_outcome(self, outcome: FeatureOutcome) -> None:
        self.progress.hide()
        label = {
            "success": "Complete",
            "partial": "Complete with warnings",
            "failed": "Failed",
            "cancelled": "Cancelled",
        }.get(outcome.status, outcome.status)
        headline = outcome.summary.splitlines()[0] if outcome.summary else label
        self._set_status(f"{label}  {headline}", outcome.status)
        self.status.setToolTip(outcome.summary)
        self.summary.setPlainText(outcome.summary)
        self.diagnostics.setPlainText("\n".join(outcome.diagnostics))
        if outcome.status in {"partial", "failed"} or outcome.diagnostics:
            self.feedback_panel.setCurrentWidget(self.diagnostics)
            self.feedback_toggle.setChecked(True)

    def submit(self, name: str, operation: Callable, on_finished: Callable | None = None) -> None:
        self.progress.setRange(0, 0)
        self.progress.show()
        self._set_status(f"{name}…", "")
        self.request_job.emit(name, operation, on_finished)

    def reset_output(self) -> None:
        # Clear on an already-empty field emits no textChanged signal. Reset
        # validation explicitly so red borders and error labels cannot linger.
        for control in tuple(self._validation_messages):
            self.clear_field_error(control)
        self.status.setToolTip("")
        self.summary.clear()
        self.diagnostics.clear()
        self._set_status("", "")

    def _set_feedback_open(self, opened: bool) -> None:
        self.feedback_toggle.setArrowType(
            Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow
        )
        self.feedback_toggle.setAccessibleName(
            "Hide activity and diagnostics" if opened else "Show activity and diagnostics"
        )
        self._feedback_animation.stop()
        if self._reduce_motion:
            self.feedback_panel.setVisible(opened)
            self.feedback_panel.setMaximumHeight(self._feedback_height if opened else 0)
            return
        if opened:
            self.feedback_panel.setMaximumHeight(0)
            self.feedback_panel.setVisible(True)
            self._feedback_animation.setStartValue(0)
            self._feedback_animation.setEndValue(self._feedback_height)
        else:
            self._feedback_animation.setStartValue(self.feedback_panel.height())
            self._feedback_animation.setEndValue(0)
        self._feedback_animation.start()

    def _feedback_animation_finished(self) -> None:
        opened = self.feedback_toggle.isChecked()
        self.feedback_panel.setVisible(opened)
        self.feedback_panel.setMaximumHeight(self._feedback_height if opened else 0)
