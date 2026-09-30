from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QStandardPaths,
    Qt,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sqltools import __version__ as APP_VERSION
from sqltools.jobs import JobManager, JobMessage
from sqltools.services import (
    FeatureOutcome,
    PreparedRun,
    cancel_prepared_run,
    commit_file_run,
)
from sqltools.theme import apply_theme

APP_NAME = "SQL Tools"
FEATURES = (
    ("INSERT_CONSOLIDATOR", "INSERT Consolidator", "sqltools.ui.insert_page", "InsertPage"),
    ("DB_AUTOMATION", "DB Automation Converter", "sqltools.ui.db_automation_page", "DbAutomationPage"),
    ("WORKFILE_GENERATOR", "Workfile Generator", "sqltools.ui.workfile_page", "WorkfilePage"),
    ("MULTI_SCHEMA", "Multi-Schema Combiner", "sqltools.ui.multi_schema_page", "MultiSchemaPage"),
    ("TABLE_COMPARE", "Table Compare", "sqltools.ui.table_compare_page", "TableComparePage"),
)
FEATURE_IDS = tuple(item[0] for item in FEATURES)


@dataclass(slots=True)
class _JobState:
    page: QWidget
    name: str
    callback: Callable | None


def _profile_path() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "generated" / "build_profile.json"
    return None


def enabled_features() -> list[str]:
    raw = os.environ.get("SQL_TOOLS_FEATURES", "").strip()
    if raw:
        requested = {part.strip().upper() for part in raw.split(",") if part.strip()}
        selected = [feature for feature in FEATURE_IDS if feature in requested]
        if selected:
            return selected
    profile_path = _profile_path()
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path else {}
        requested = {str(item).upper() for item in profile.get("enabled_features", [])}
    except (OSError, ValueError, AttributeError):
        requested = set()
    selected = [feature for feature in FEATURE_IDS if feature in requested]
    return selected or list(FEATURE_IDS)


def _configure_logging() -> None:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not location:
        return
    try:
        directory = Path(location)
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "sql-tools.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("sqltools")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


class MainWindow(QMainWindow):
    def __init__(self, features: list[str] | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1240, 790)
        self.setMinimumSize(min(800, available.width()), min(440, available.height()))
        width, height = min(1240, available.width()), min(790, available.height())
        self.resize(width, height)
        self.move(available.center() - self.rect().center())
        self.settings = QSettings()
        self.features = features or enabled_features()
        self.job_manager = JobManager(self)
        self.jobs: dict[str, _JobState] = {}
        self._closing_after_job = False
        self.pages: list[QWidget] = []
        self.nav_buttons: list[QToolButton] = []

        central = QWidget()
        central.setObjectName("workspace")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        self.sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._load_pages()
        self._build_menu()
        self._restore_state()
        self._move_nav_marker(self.stack.currentIndex(), animate=False)

        self.job_manager.started.connect(self._job_started)
        self.job_manager.progress.connect(self._job_progress)
        self.job_manager.completed.connect(self._job_completed)
        self.job_manager.busy_changed.connect(self._busy_changed)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(204)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(5)
        brand = QLabel("SQL Tools")
        brand.setObjectName("brand")
        brand.setContentsMargins(7, 4, 7, 4)
        layout.addWidget(brand)
        self.nav_layout = QVBoxLayout()
        self.nav_layout.setContentsMargins(0, 12, 0, 0)
        self.nav_layout.setSpacing(5)
        layout.addLayout(self.nav_layout)
        layout.addStretch(1)
        footer = QLabel(f"Version {APP_VERSION}")
        footer.setObjectName("versionLabel")
        footer.setContentsMargins(7, 6, 7, 3)
        layout.addWidget(footer)
        self.nav_marker = QFrame(sidebar)
        self.nav_marker.setObjectName("navMarker")
        self.nav_marker.setFixedWidth(3)
        self.nav_marker.setStyleSheet("background: #623A96; border-radius: 1px;")
        self.nav_marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.nav_marker_animation = QPropertyAnimation(self.nav_marker, b"geometry", self)
        self.nav_marker_animation.setDuration(100)
        self.nav_marker_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        return sidebar

    def _load_pages(self) -> None:
        mapping = {feature: (title, module_name, class_name) for feature, title, module_name, class_name in FEATURES}
        if not self.features:
            empty = QLabel("No features are enabled in this build profile.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stack.addWidget(empty)
            return
        for feature in self.features:
            title, module_name, class_name = mapping[feature]
            page_type = getattr(importlib.import_module(module_name), class_name)
            page = page_type(self)
            page.clear_shell_status_requested.connect(self._clear_shell_status)
            page.request_job.connect(lambda name, operation, callback, page=page: self._start_job(
                page, name, operation, callback
            ))
            self.pages.append(page)
            self.stack.addWidget(page)
            button = QToolButton()
            short_titles = {
                "INSERT Consolidator": "INSERT Consolidator",
                "DB Automation Converter": "DB Automation",
                "Workfile Generator": "Workfile Generator",
                "Multi-Schema Combiner": "Multi-Schema",
                "Table Compare": "Table Compare",
            }
            button.setText(short_titles.get(title, title))
            button.setAccessibleName(title)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setObjectName("navItem")
            button.setMinimumHeight(38)
            page_index = len(self.pages) - 1
            button.clicked.connect(
                lambda checked=False, index=page_index: self._select_page(index)
            )
            self.nav_buttons.append(button)
            self.nav_layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        view_menu = self.menuBar().addMenu("View")
        self.reduce_motion_action = QAction("Reduce motion", self, checkable=True)
        self.reduce_motion_action.setChecked(
            self.settings.value("view/reduce_motion", False, type=bool)
        )
        self.reduce_motion_action.toggled.connect(self._set_reduce_motion)
        view_menu.addAction(self.reduce_motion_action)
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About SQL Tools", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        self._set_reduce_motion(self.reduce_motion_action.isChecked())

        status = self.statusBar()
        self.cancel_button = QPushButton("Cancel operation")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_job)
        status.addPermanentWidget(self.cancel_button)

    def _restore_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            if not available.intersects(self.frameGeometry()):
                self.move(available.center() - self.rect().center())
            self.resize(min(self.width(), available.width()), min(self.height(), available.height()))
        selected = self.settings.value("window/selected_feature", "")
        for index, feature in enumerate(self.features):
            if feature == selected:
                self._select_page(index)
                break

    def _select_page(self, index: int) -> None:
        if not 0 <= index < len(self.pages):
            return
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons):
            button.setChecked(position == index)
        self.settings.setValue("window/selected_feature", self.features[index])
        self._move_nav_marker(index)

    def _move_nav_marker(self, index: int, *, animate: bool = True) -> None:
        if not 0 <= index < len(self.nav_buttons):
            return
        self.nav_layout.activate()
        button = self.nav_buttons[index]
        point = button.mapTo(self.sidebar, QPoint(0, 0))
        target = QRect(4, point.y() + 4, 3, max(20, button.height() - 8))
        self.nav_marker_animation.stop()
        if not animate or self.reduce_motion_action.isChecked():
            self.nav_marker.setGeometry(target)
            return
        self.nav_marker_animation.setStartValue(self.nav_marker.geometry())
        self.nav_marker_animation.setEndValue(target)
        self.nav_marker_animation.start()

    def _set_reduce_motion(self, enabled: bool) -> None:
        self.settings.setValue("view/reduce_motion", enabled)
        for page in self.pages:
            page.set_reduce_motion(enabled)
        if enabled:
            self.nav_marker_animation.stop()
            self._move_nav_marker(self.stack.currentIndex(), animate=False)

    def _clear_shell_status(self) -> None:
        if not self.job_manager.busy:
            self.statusBar().clearMessage()

    def _start_job(self, page, name: str, operation: Callable, callback: Callable | None) -> None:
        try:
            job_id = self.job_manager.submit(name, operation)
        except RuntimeError as error:
            page.status.setText(str(error))
            return
        self.jobs[job_id] = _JobState(page, name, callback)

    def _job_started(self, job_id: str, name: str) -> None:
        self.statusBar().showMessage(name)
        for page in self.pages:
            page.set_busy(True)
        self.cancel_button.setVisible(True)

    def _job_progress(self, job_id: str, message: str, value: int) -> None:
        state = self.jobs.get(job_id)
        if state:
            state.page.show_progress(message, value)
        self.statusBar().showMessage(message)

    def _busy_changed(self, busy: bool) -> None:
        # A completed preparation can synchronously start its commit job before the
        # previous worker emits its final busy=False notification.
        busy = self.job_manager.busy
        if not busy:
            for page in self.pages:
                page.set_busy(False)
            self.cancel_button.setVisible(False)

    def _job_completed(self, message: JobMessage) -> None:
        state = self.jobs.pop(message.job_id, None)
        if state is None:
            return
        if message.error:
            if message.error == "Operation cancelled.":
                outcome = FeatureOutcome("Operation cancelled.", status="cancelled")
            else:
                self._log_failure(state.name, message)
                outcome = FeatureOutcome(
                    "The operation could not be completed. See Diagnostics for details.",
                    [f"{message.error_type or 'Error'}: {message.error}"],
                    status="failed",
                )
            state.page.set_outcome(outcome)
            if state.callback:
                state.callback(outcome)
            self.statusBar().showMessage(outcome.status.title())
            self._finish_close_if_requested()
            return

        if isinstance(message.result, PreparedRun):
            self._confirm_and_commit(state, message.result)
            return

        result = message.result
        if isinstance(result, FeatureOutcome):
            if result.clipboard_text is not None:
                QApplication.clipboard().setText(result.clipboard_text)
            state.page.set_outcome(result)
            if state.callback:
                state.callback(result)
            self.statusBar().showMessage(result.status.title())
        elif state.callback:
            state.callback(result)
            state.page.progress.hide()
            self.statusBar().showMessage("Complete")
        else:
            state.page.set_outcome(FeatureOutcome("Complete."))
            self.statusBar().showMessage("Complete")
        self._finish_close_if_requested()

    def _confirm_and_commit(self, state: _JobState, prepared: PreparedRun) -> None:
        if prepared.existing:
            paths = [path.name for path, _fingerprint in prepared.existing]
            shown = paths[:12]
            detail = "\n".join(f"• {name}" for name in shown)
            if len(paths) > len(shown):
                detail += f"\n… and {len(paths) - len(shown):,} more"
            answer = QMessageBox.question(
                self,
                "Replace existing outputs?",
                f"{len(paths):,} output file(s) already exist. Replace them?\n\n{detail}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                cancel_prepared_run(prepared)
                state.page.set_outcome(FeatureOutcome("No files were changed.", status="cancelled"))
                self.statusBar().showMessage("Output review cancelled")
                self._finish_close_if_requested()
                return

        try:
            job_id = self.job_manager.submit(
                f"Saving {len(prepared.artifacts):,} output file(s)",
                lambda context: commit_file_run(context, prepared),
            )
        except RuntimeError as error:
            cancel_prepared_run(prepared)
            state.page.set_outcome(FeatureOutcome(str(error), status="failed"))
            return
        self.jobs[job_id] = state

    def _cancel_job(self) -> None:
        self.job_manager.cancel()
        self.statusBar().showMessage("Cancellation requested…")

    def _log_failure(self, name: str, message: JobMessage) -> None:
        frames = (message.traceback_text or "").splitlines()
        # Drop the final exception line because third-party error messages can echo input text.
        stack = "\n".join(frames[:-1])
        logging.getLogger("sqltools").error("%s failed: %s\n%s", name, "WorkerError", stack)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME} {APP_VERSION}</b><br>SQL release preparation and table comparison.<br><br>"
            f"Python {sys.version_info.major}.{sys.version_info.minor} · {sys.platform}",
        )

    def closeEvent(self, event) -> None:
        if self.job_manager.busy:
            answer = QMessageBox.question(
                self,
                "Operation in progress",
                "A background operation is running. Cancel it and close when it stops?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing_after_job = True
            self._cancel_job()
            event.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        event.accept()

    def _finish_close_if_requested(self) -> None:
        if self._closing_after_job and not self.job_manager.busy:
            self._closing_after_job = False
            self.close()


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setOrganizationName("SQLTools")
    app.setOrganizationDomain("sqltools.example")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    _configure_logging()
    apply_theme(app)

    if smoke_test:
        from logic import table_comparator

        sample = table_comparator.parse_workbench_csv_compact("id,value\n1,ok\n")
        if sample.columns != ("id", "value") or len(sample.rows) != 1:
            return 2
        compared = table_comparator.compare_compact(
            [("A", sample), ("B", sample)], "id", included_columns={"id", "value"}
        )
        window = MainWindow()
        if len(window.pages) != len(window.features) or compared.counts["identical"] != 1:
            return 3
        if sys.stdout is not None:
            print("SQL Tools GUI, feature pages, and parser smoke test passed")
        window.deleteLater()
        return 0

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
