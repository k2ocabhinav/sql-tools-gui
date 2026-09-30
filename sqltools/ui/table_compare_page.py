from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from logic import table_comparator as logic
from sqltools.services import FeatureOutcome, prepare_file_run
from sqltools.theme import COLORS
from sqltools.ui.base import FeaturePage
from sqltools.ui.widgets import CheckBox, run_button

_INVALID_INDEX = QModelIndex()


def _cell_text(value: str | None) -> str:
    if value is None:
        return "⟂ SQL NULL"
    if value == "":
        return "⟨empty string⟩"
    if value == "NULL":
        return '"NULL"'
    return value


class SourcesModel(QAbstractTableModel):
    renameRequested = Signal(int, str)
    HEADERS = ("Label", "Format", "Rows", "File")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sources: list[tuple[str, logic.TableData, dict]] = []

    def rowCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.sources)

    def columnCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        label, table, _info = self.sources[index.row()]
        values = (label, table.export_format.upper(), f"{len(table.rows):,}", Path(table.file_path).name)
        return values[index.column()]

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.EditRole:
            return False
        self.renameRequested.emit(index.row(), str(value).strip())
        return True

    def replace(self, sources: list[tuple[str, logic.TableData, dict]]) -> None:
        self.beginResetModel()
        self.sources = list(sources)
        self.endResetModel()

    def notify_label(self, row: int) -> None:
        if self.sources and 0 <= row < len(self.sources):
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))


class ComparisonTableModel(QAbstractTableModel):
    sortRequested = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: logic.CompactComparison | None = None
        self.visible: list[int] = []
        self.headers: tuple[str, ...] = ()
        self.show_identical = False

    def rowCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.visible)

    def columnCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable if index.isValid() else Qt.ItemFlag.NoItemFlags

    def _display_cell(self, row_index: int, column_index: int) -> str:
        result = self.result
        row = result.rows[row_index]
        if result.two_way:
            label_a, label_b = result.sources[0][0], result.sources[1][0]
            status_labels = {
                "identical": "Match",
                "changed": "Changed",
                "only_a": f"{label_a} only",
                "only_b": f"{label_b} only",
            }
            if column_index == 0:
                return status_labels[row.status]
            position = column_index - 1
            name = result.columns[position]
            source_a, source_b = row.source_rows
            if source_a is None:
                value = result.sources[1][1].rows[source_b][result.sources[1][1].column_index[name]]
                return _cell_text(value)
            table_a = result.sources[0][1]
            value_a = table_a.rows[source_a][table_a.column_index[name]]
            if source_b is None:
                return _cell_text(value_a)
            if position not in row.diff_columns:
                return _cell_text(value_a)
            table_b = result.sources[1][1]
            value_b = table_b.rows[source_b][table_b.column_index[name]]
            return f"{_cell_text(value_a)}  →  {_cell_text(value_b)}"

        if column_index == 0:
            return {
                "ok": "Match", "data_diff": "Data drift", "missing": "Missing",
                "missing_and_diff": "Missing + drift",
            }[row.status]
        if column_index == 1:
            return _cell_text(row.key)
        if column_index == 2:
            return f"{row.present_count}/{len(result.sources)}"
        if column_index == 3:
            return f"{row.match_count}/{len(result.sources)}"
        return ", ".join(result.columns[position] for position in row.diff_columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.result is None:
            return None
        result_row = self.result.rows[self.visible[index.row()]]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_cell(self.visible[index.row()], index.column())
        if role == Qt.ItemDataRole.UserRole:
            return self.visible[index.row()]
        if role == Qt.ItemDataRole.BackgroundRole:
            from PySide6.QtGui import QColor
            colors = {
                "only_a": COLORS["diff_a"], "only_b": COLORS["diff_b"],
                "changed": COLORS["diff_changed"], "missing": COLORS["diff_a"],
                "missing_and_diff": COLORS["diff_changed"],
                "data_diff": COLORS["diff_changed"],
            }
            return QColor(colors[result_row.status]) if result_row.status in colors else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return result_row.status.replace("_", " ").title()
        return None

    def set_result(self, result: logic.CompactComparison | None, show_identical: bool) -> None:
        self.beginResetModel()
        self.result = result
        self.show_identical = show_identical
        if result is None:
            self.visible = []
            self.headers = ()
        else:
            self.visible = list(range(len(result.rows)))
            self.headers = (
                ("Status", *result.columns)
                if result.two_way else
                ("Status", result.key_column, "Present", "Match", "Differing columns")
            )
            if not show_identical:
                identical = "identical" if result.two_way else "ok"
                self.visible = [i for i, row in enumerate(result.rows) if row.status != identical]
        self.endResetModel()

    def set_visible(self, indices: list[int]) -> None:
        self.beginResetModel()
        self.visible = indices
        self.endResetModel()

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.sortRequested.emit(column, order)


class DetailTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers: tuple[str, ...] = ()
        self.rows: tuple[tuple[str, ...], ...] = ()

    def rowCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=_INVALID_INDEX):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return self.rows[index.row()][index.column()]
        return None

    def set_values(self, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> None:
        self.beginResetModel()
        self.headers, self.rows = headers, rows
        self.endResetModel()


class TableComparePage(FeaturePage):
    def __init__(self, parent=None):
        super().__init__(
            "Table Compare",
            "Compare exported tables and inspect row differences.", parent,
        )
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.setObjectName("compareWorkspace")
        self.workspace_splitter.setHandleWidth(8)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        setup_host = QWidget()
        self.setup_layout = QVBoxLayout(setup_host)
        self.setup_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_layout.setSpacing(8)
        results_host = QWidget()
        self.results_layout = QVBoxLayout(results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.setup_host = setup_host
        self.results_host = results_host
        self.workspace_splitter.addWidget(setup_host)
        self.workspace_splitter.addWidget(results_host)

        self.sources: list[tuple[str, logic.TableData, dict]] = []
        self.result: logic.CompactComparison | None = None
        self.input_revision = 0
        self.column_checks: dict[str, CheckBox] = {}
        self._column_selected: dict[str, bool] = {}
        self._common_columns: list[str] = []
        self._busy = False
        self._compact_results = False
        self._details_dialog: QDialog | None = None
        self._detail_dismissed = False

        self.source_section, source_group = self.add_group("Sources", self.setup_layout)
        source_toolbar = QWidget()
        source_toolbar.setObjectName("tableCompareSourceToolbar")
        source_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        source_buttons = QHBoxLayout(source_toolbar)
        source_buttons.setContentsMargins(0, 0, 0, 0)
        source_buttons.setSpacing(8)
        add = QPushButton("Add exports…")
        remove = QPushButton("Remove")
        clear = QPushButton("Clear inputs")
        clear.setEnabled(False)
        add.clicked.connect(self._add_files)
        remove.clicked.connect(self._remove_selected)
        clear.clicked.connect(self._clear_sources)
        self._source_mutation_buttons = [add, remove]
        self.remove_source_button = remove
        self.clear_sources_button = clear
        source_buttons.addWidget(add)
        source_buttons.addWidget(remove)
        source_buttons.addStretch(1)
        source_buttons.addWidget(clear)
        source_group.addWidget(source_toolbar)

        self.sources_model = SourcesModel(self)
        self.sources_view = QTableView()
        self.sources_view.setModel(self.sources_model)
        self.sources_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.sources_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.sources_view.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.EditKeyPressed
        )
        self.sources_view.setMinimumHeight(96)
        self.sources_view.setMaximumHeight(128)
        self.sources_view.verticalHeader().hide()
        self.sources_view.verticalHeader().setDefaultSectionSize(24)
        source_header = self.sources_view.horizontalHeader()
        source_header.setSectionResizeMode(0, source_header.ResizeMode.Interactive)
        source_header.setSectionResizeMode(1, source_header.ResizeMode.Interactive)
        source_header.setSectionResizeMode(2, source_header.ResizeMode.Interactive)
        source_header.setSectionResizeMode(3, source_header.ResizeMode.Stretch)
        self.sources_view.setColumnWidth(0, 130)
        self.sources_view.setColumnWidth(1, 76)
        self.sources_view.setColumnWidth(2, 76)
        source_group.addWidget(self.sources_view)

        self.sources_model.renameRequested.connect(self._rename_source_row)
        self.sources_view.selectionModel().selectionChanged.connect(self._source_selected)

        self.comparison_section = QWidget()
        comparison_layout = QVBoxLayout(self.comparison_section)
        comparison_layout.setContentsMargins(0, 0, 0, 0)
        comparison_group = comparison_layout
        compare_row = QWidget()
        compare_controls = QHBoxLayout(compare_row)
        compare_controls.setContentsMargins(0, 0, 0, 0)
        compare_controls.setSpacing(8)
        key_label = QLabel("Key column")
        self.key_combo = QComboBox()
        self.key_combo.setMinimumWidth(120)
        self.key_combo.setMaximumWidth(240)
        self.key_combo.currentTextChanged.connect(self._sync_key_checkbox)
        self.key_combo.currentTextChanged.connect(self._invalidate_result)
        self.columns_more_button = QPushButton("Columns (0 of 0)…")
        self.columns_more_button.clicked.connect(self._open_columns_dialog)
        self.compare_button = run_button("Compare")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self._compare)
        compare_controls.addWidget(key_label)
        compare_controls.addWidget(self.key_combo, 1)
        compare_controls.addWidget(self.columns_more_button)
        compare_controls.addStretch(1)
        compare_controls.addWidget(self.compare_button)
        comparison_group.addWidget(compare_row)
        self.setup_layout.addWidget(self.comparison_section)

        self.compact_empty_hint = QLabel(
            "Add at least two exports to compare; results will appear here."
        )
        self.compact_empty_hint.setObjectName("muted")
        self.compact_empty_hint.setWordWrap(True)
        self.compact_empty_hint.hide()
        self.setup_layout.addWidget(self.compact_empty_hint)

        self.compact_summary = QLabel()
        self.compact_summary.setObjectName("muted")
        self.compact_edit_button = QPushButton("Edit setup")
        self.compact_edit_button.clicked.connect(self._expand_setup)
        self.compact_setup = QWidget()
        compact_row = QHBoxLayout(self.compact_setup)
        compact_row.setContentsMargins(0, 0, 0, 0)
        compact_row.addWidget(self.compact_summary, 1)
        compact_row.addWidget(self.compact_edit_button)
        self.compact_setup.hide()
        self.setup_layout.addWidget(self.compact_setup)

        self.result_toolbar = QWidget()
        result_toolbar_row = QHBoxLayout(self.result_toolbar)
        result_toolbar_row.setContentsMargins(0, 0, 0, 0)
        result_toolbar_row.setSpacing(8)
        self.results_title = QLabel("Results")
        self.results_title.setObjectName("sectionTitle")
        self.details_button = QPushButton("View selected row…")
        self.details_button.clicked.connect(self._show_detail_dialog)
        self.details_button.hide()
        self.export_button = QPushButton("Export to Excel…")
        self.copy_button = QPushButton("Copy summary")
        self.export_button.clicked.connect(self._export)
        self.copy_button.clicked.connect(self._copy_summary)
        self.export_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        result_toolbar_row.addWidget(self.results_title)
        result_toolbar_row.addStretch(1)
        result_toolbar_row.addWidget(self.details_button)
        result_toolbar_row.addWidget(self.export_button)
        result_toolbar_row.addWidget(self.copy_button)
        self.results_layout.addWidget(self.result_toolbar)

        self.result_filters = QWidget()
        result_filters_row = QHBoxLayout(self.result_filters)
        result_filters_row.setContentsMargins(0, 0, 0, 0)
        result_filters_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search compared values and differing columns")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._schedule_filter)
        self.status_filter = QComboBox()
        self.status_filter.setMinimumWidth(146)
        self.status_filter.addItem("All statuses", "all")
        for code, label in (("changed", "Changed / drift"), ("only_a", "Only source A"),
                            ("only_b", "Only source B"), ("missing", "Missing"),
                            ("missing_and_diff", "Missing + drift"), ("ok", "Match"),
                            ("identical", "Identical")):
            self.status_filter.addItem(label, code)
        self.status_filter.currentIndexChanged.connect(self._status_filter_changed)
        self.show_identical = CheckBox("Show matching rows")
        self.show_identical.setChecked(False)
        self.show_identical.stateChanged.connect(self._display_option_changed)
        result_filters_row.addWidget(self.search, 1)
        result_filters_row.addWidget(self.status_filter)
        result_filters_row.addWidget(self.show_identical)
        self.results_layout.addWidget(self.result_filters)

        self.summary_label = QLabel("Add at least two exports, choose a key, then compare.")
        self.summary_label.setObjectName("muted")
        self.summary_label.setWordWrap(True)
        self.results_layout.addWidget(self.summary_label)

        self.results_empty_state = QWidget()
        empty_state_layout = QVBoxLayout(self.results_empty_state)
        empty_state_layout.setContentsMargins(24, 12, 24, 12)
        empty_state_layout.setSpacing(6)
        empty_state_layout.addStretch(1)
        self.results_empty_title = QLabel("No comparison results yet")
        self.results_empty_title.setObjectName("sectionTitle")
        self.results_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_empty_hint = QLabel()
        self.results_empty_hint.setObjectName("muted")
        self.results_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_empty_hint.setWordWrap(True)
        empty_state_layout.addWidget(self.results_empty_title)
        empty_state_layout.addWidget(self.results_empty_hint)
        empty_state_layout.addStretch(1)
        self.results_layout.addWidget(self.results_empty_state, 1)

        self.result_model = ComparisonTableModel(self)
        self.result_model.sortRequested.connect(self._sort_requested)
        self.result_view = QTableView()
        self.result_view.setModel(self.result_model)
        self.result_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.result_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.result_view.setSortingEnabled(True)
        self.result_view.horizontalHeader().setStretchLastSection(True)
        self.result_view.horizontalHeader().setDefaultSectionSize(150)
        self.result_view.verticalHeader().hide()
        self.result_view.verticalHeader().setDefaultSectionSize(24)
        self.result_view.setAlternatingRowColors(True)
        self.result_view.setMinimumHeight(115)
        self.result_view.hide()
        self.results_layout.addWidget(self.result_view, 1)

        self.details_row = QWidget()
        detail_controls = QHBoxLayout(self.details_row)
        detail_controls.setContentsMargins(0, 0, 0, 0)
        self.detail_label = QLabel("Selected row details")
        self.detail_label.setObjectName("sectionTitle")
        self.details_hide_button = QPushButton("Hide")
        self.details_hide_button.clicked.connect(self._dismiss_detail)
        detail_controls.addWidget(self.detail_label)
        detail_controls.addStretch(1)
        detail_controls.addWidget(self.details_hide_button)
        self.results_layout.addWidget(self.details_row)
        self.details_row.hide()

        self.detail_model = DetailTableModel(self)
        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.verticalHeader().hide()
        self.detail_view.setMaximumHeight(138)
        self.detail_view.horizontalHeader().setStretchLastSection(True)
        self.detail_view.hide()
        self.results_layout.addWidget(self.detail_view)
        self.result_view.selectionModel().selectionChanged.connect(self._selection_changed)
        # Model resets (filtering, sorting, new results) silently drop the selection.
        self.result_model.modelReset.connect(self._sync_detail_presentation)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self._apply_filter)
        self.set_workspace_widget(self.workspace_splitter)
        self.actions_row.hide()
        self.workspace_splitter.setSizes([250, 480])
        self._sync_results_presentation()
        self._source_selected()

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self._busy = busy
        self.export_button.setEnabled(not busy and self.result is not None)
        self.copy_button.setEnabled(not busy and self.result is not None)
        self.search.setEnabled(not busy)
        self.status_filter.setEnabled(not busy)
        self.sources_view.setEnabled(not busy)
        self.show_identical.setEnabled(not busy)
        self.result_view.setEnabled(not busy)
        self.key_combo.setEnabled(not busy and bool(self._common_columns))
        self.columns_more_button.setEnabled(not busy and bool(self._common_columns))
        self._update_compare_button()
        self._sync_results_presentation()
        self.details_button.setEnabled(
            not busy and self.result is not None and self._selected_result_row() is not None
        )
        for button in self._source_mutation_buttons:
            button.setEnabled(not busy)
        self._source_selected()
        self.clear_sources_button.setEnabled(not busy and bool(self.sources))

    def _update_compare_button(self) -> None:
        can_compare = (
            len(self.sources) >= 2
            and bool(self._common_columns)
            and bool(self.key_combo.currentText())
        )
        self.compare_button.setEnabled(not self._busy and can_compare)

    def _sync_results_presentation(self) -> None:
        has_result = self.result is not None
        self.result_toolbar.setVisible(has_result)
        self.result_filters.setVisible(has_result)
        self.summary_label.setVisible(has_result)
        self.results_empty_state.setVisible(not has_result)
        self.result_view.setVisible(has_result)
        if has_result:
            return
        self.results_empty_hint.setText(self._readiness_message())

    def _readiness_message(self) -> str:
        """Explain the next step; the wording follows what Compare needs right now."""
        if self._busy:
            return "Results will appear here when the current operation finishes."
        if len(self.sources) < 2:
            return "Add at least two exports and run Compare to inspect their differences."
        if not self._common_columns:
            return "These exports share no columns. Choose files with a common key column."
        if not self.key_combo.currentText():
            return "Select a shared key column to enable Compare."
        return "Run Compare to inspect matching rows and differences."

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_detail_presentation()
        compact = self.height() < 600
        if compact == self._compact_results:
            return
        self._compact_results = compact
        if compact and self.result is not None:
            self.results_host.show()
            self.compact_empty_hint.hide()
            self._collapse_setup()
        elif compact:
            self.results_host.hide()
            self.source_section.show()
            self.comparison_section.show()
            self.compact_setup.hide()
            self._sync_compact_empty_hint()
        else:
            self.results_host.show()
            self.compact_empty_hint.hide()
            self._expand_setup()

    def _sync_compact_empty_hint(self) -> None:
        show_hint = self.height() < 600 and self.result is None and self.results_host.isHidden()
        if show_hint:
            if len(self.sources) < 2:
                message = "Add at least two exports to compare; results will appear here."
            elif self._common_columns and self.key_combo.currentText() and not self._busy:
                message = "Comparison results will appear here after you run Compare."
            else:
                message = self._readiness_message()
            self.compact_empty_hint.setText(message)
        self.compact_empty_hint.setVisible(show_hint)

    def _collapse_setup(self) -> None:
        self.source_section.hide()
        self.comparison_section.hide()
        self.compact_empty_hint.hide()
        count = len(self.sources)
        key = self.key_combo.currentText() or "No key selected"
        self.compact_summary.setText(f"{count} sources  ·  Key: {key}")
        self.compact_setup.show()
        self.workspace_splitter.setSizes([42, max(120, self.workspace_splitter.height() - 42)])

    def _expand_setup(self) -> None:
        self.compact_setup.hide()
        self.source_section.show()
        self.comparison_section.show()
        available = max(260, self.workspace_splitter.height())
        setup_size = min(250, max(150, available - 115)) if self._compact_results else 250
        self.workspace_splitter.setSizes([setup_size, max(115, available - setup_size)])

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select table exports", "",
            "Table exports (*.sql *.csv);;SQL files (*.sql);;CSV files (*.csv)",
        )
        paths = [path for path in paths if all(path != table.file_path for _, table, _ in self.sources)]
        if not paths:
            return
        self._invalidate_result()
        revision = self.input_revision
        existing_labels = {name for name, _, _ in self.sources}

        def load(context):
            loaded = []
            for position, path in enumerate(paths, 1):
                context.check_cancelled()
                context.report(f"Loading {Path(path).name}", round(position * 100 / len(paths)))
                table = logic.load_export_file_compact(path, check_cancelled=context.check_cancelled)
                info = logic.infer_source_label(path, {"schema": table.schema})
                label = info["label"]
                used = existing_labels | {name for name, _, _ in loaded}
                base, suffix = label, 2
                while label in used:
                    label = f"{base} ({suffix})"
                    suffix += 1
                loaded.append((label, table, info))
            return loaded

        def loaded(result):
            if revision != self.input_revision or not isinstance(result, list):
                return
            self.sources.extend(result)
            self._refresh_sources()

        self.reset_output()
        self.submit("Loading table exports", load, loaded)

    def _refresh_sources(self) -> None:
        self.sources_model.replace(self.sources)
        self.clear_sources_button.setEnabled(not self._busy and bool(self.sources))
        columns = []
        if self.sources:
            shared = set(self.sources[0][1].columns)
            for _, table, _ in self.sources[1:]:
                shared.intersection_update(table.columns)
            columns = [name for name in self.sources[0][1].columns if name in shared]
        self._common_columns = columns
        old = self.key_combo.currentText()
        self.key_combo.blockSignals(True)
        self.key_combo.clear()
        self.key_combo.addItems(columns)
        if old in columns:
            self.key_combo.setCurrentText(old)
        self.key_combo.blockSignals(False)
        previous_states = dict(self._column_selected)
        self.column_checks = {}
        self._column_selected = {name: previous_states.get(name, True) for name in columns}
        self._update_column_caption()
        self._sync_key_checkbox()
        self.key_combo.setEnabled(not self._busy and bool(columns))
        self._update_column_caption()

        table_names = sorted({table.table_name for _, table, _ in self.sources if table.table_name})
        warning_count = sum(len(table.warnings) for _, table, _ in self.sources)
        warning_parts = []
        if len(table_names) > 1:
            warning_parts.append(f"Different table names detected: {', '.join(table_names)}.")
        if warning_count:
            warning_parts.append(f"{warning_count:,} parser warning(s); inspect Diagnostics.")
        self.diagnostics.setPlainText("\n".join(warning_parts))
        self.summary_label.setText(
            f"{len(self.sources)} source(s) loaded. Select a key and compare."
            if self.sources else "Add at least two exports to compare."
        )
        self._invalidate_result()

    def _sync_key_checkbox(self, *_args) -> None:
        key = self.key_combo.currentText()
        if key:
            self._column_selected[key] = True
        for name, checkbox in self.column_checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self._column_selected.get(name, True))
            checkbox.setEnabled(not self._busy and name != key)
            checkbox.blockSignals(False)
        self._update_column_caption()

    def _column_selection_changed(self, name: str, checked: bool) -> None:
        if name != self.key_combo.currentText():
            self._column_selected[name] = checked
        self._update_column_caption()
        self._invalidate_result()

    def _set_all_columns(self, enabled: bool) -> None:
        key = self.key_combo.currentText()
        for name in self._common_columns:
            self._column_selected[name] = True if name == key else enabled
        for name, checkbox in self.column_checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(self._column_selected[name])
            checkbox.blockSignals(False)
        self._update_column_caption()
        self._invalidate_result()

    def _update_column_caption(self) -> None:
        selected = sum(self._column_selected.values())
        self.columns_more_button.setText(f"Columns ({selected} of {len(self._common_columns)})…")

    def _open_columns_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose columns to compare")
        dialog.resize(480, 430)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Search columns")
        layout.addWidget(search)
        column_list = QListWidget()
        key = self.key_combo.currentText()
        for name in self._common_columns:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked if self._column_selected[name] else Qt.CheckState.Unchecked
            )
            if name == key:
                item.setText(f"{name}  ·  key, always included")
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            column_list.addItem(item)
        layout.addWidget(column_list, 1)

        def filter_columns(query: str) -> None:
            needle = query.casefold().strip()
            for row in range(column_list.count()):
                column_list.setRowHidden(
                    row, bool(needle) and needle not in column_list.item(row).text().casefold()
                )

        search.textChanged.connect(filter_columns)
        bulk_row = QHBoxLayout()
        choose_all = QPushButton("Select all")
        choose_none = QPushButton("Clear selection")
        choose_all.clicked.connect(
            lambda: self._set_dialog_columns(column_list, True, key)
        )
        choose_none.clicked.connect(
            lambda: self._set_dialog_columns(column_list, False, key)
        )
        bulk_row.addWidget(choose_all)
        bulk_row.addWidget(choose_none)
        bulk_row.addStretch(1)
        layout.addLayout(bulk_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._column_selected = {
            column_list.item(row).data(Qt.ItemDataRole.UserRole): (
                True if column_list.item(row).data(Qt.ItemDataRole.UserRole) == key else
                column_list.item(row).checkState() == Qt.CheckState.Checked
            )
            for row in range(column_list.count())
        }
        self._sync_key_checkbox()
        self._update_column_caption()
        self._invalidate_result()

    @staticmethod
    def _set_dialog_columns(column_list: QListWidget, enabled: bool, key: str) -> None:
        for row in range(column_list.count()):
            item = column_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) != key:
                item.setCheckState(
                    Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
                )

    def _selected_source_row(self) -> int:
        rows = self.sources_view.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _remove_selected(self) -> None:
        row = self._selected_source_row()
        if 0 <= row < len(self.sources):
            self.sources.pop(row)
            self._refresh_sources()

    def _clear_sources(self) -> None:
        self.sources.clear()
        self._refresh_sources()

    def _source_selected(self) -> None:
        selected = 0 <= self._selected_source_row() < len(self.sources)
        self.remove_source_button.setEnabled(selected and not self._busy)

    def _rename_source_row(self, row: int, value: str) -> None:
        if not (0 <= row < len(self.sources)):
            return
        if not value:
            self.status.setText("Source labels cannot be empty.")
            self.sources_model.dataChanged.emit(
                self.sources_model.index(row, 0), self.sources_model.index(row, 0)
            )
            return
        if any(i != row and source[0] == value for i, source in enumerate(self.sources)):
            self.status.setText("Source labels must be unique.")
            self.sources_model.dataChanged.emit(
                self.sources_model.index(row, 0), self.sources_model.index(row, 0)
            )
            return
        old = self.sources[row]
        self.sources[row] = (value, old[1], {**old[2], "label": value})
        self.sources_model.replace(self.sources)
        self._invalidate_result()

    def _invalidate_result(self, *_args) -> None:
        self.input_revision += 1
        self.result = None
        self._reset_result_filters()
        self.result_model.set_result(None, False)
        self._clear_detail()
        self.export_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self._set_status("", "")
        if self.sources:
            self.summary_label.setText("Inputs changed. Compare again.")
        else:
            self.summary_label.setText("Add at least two exports to compare.")
        self._sync_compact_empty_hint()
        self._update_compare_button()
        self._sync_results_presentation()

    def _reset_result_filters(self) -> None:
        """A new result starts unfiltered so visible filters always match visible rows."""
        self._filter_timer.stop()
        with QSignalBlocker(self.search):
            self.search.clear()
        with QSignalBlocker(self.status_filter):
            self.status_filter.setCurrentIndex(0)

    def _compare(self) -> None:
        if len(self.sources) < 2:
            self.set_field_error(self.sources_view, "Load at least two exports.")
            return
        key = self.key_combo.currentText()
        if not key:
            self.set_field_error(self.key_combo, "Select a key column.")
            return
        revision = self.input_revision
        sources = tuple((label, table) for label, table, _ in self.sources)
        included_columns = {
            name for name, selected in self._column_selected.items() if selected
        }
        included_columns.add(key)
        self.result = None
        self._reset_result_filters()
        self.result_model.set_result(None, False)
        self._clear_detail()
        self.export_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self._sync_results_presentation()
        self.reset_output()

        def compare(context):
            context.report("Comparing rows")
            context.check_cancelled()
            result = logic.compare_compact(
                sources,
                key,
                included_columns=included_columns,
                check_cancelled=context.check_cancelled,
            )
            context.report("Comparison ready", 100)
            return result

        def complete(result):
            if revision != self.input_revision or not isinstance(result, logic.CompactComparison):
                return
            self.result = result
            self.result_model.set_result(result, self.show_identical.isChecked())
            self._sync_results_presentation()
            self.export_button.setEnabled(True)
            self.copy_button.setEnabled(True)
            counts = result.counts
            if result.two_way:
                text = (
                    f"{counts['identical']:,} identical   ·   {counts['changed']:,} changed   ·   "
                    f"{counts['only_a']:,} only in {result.sources[0][0]}   ·   "
                    f"{counts['only_b']:,} only in {result.sources[1][0]}"
                )
            else:
                text = (
                    f"{counts['ok']:,} match everywhere   ·   {counts['data_diff']:,} data drift   ·   "
                    f"{counts['missing']:,} missing   ·   {counts['missing_and_diff']:,} missing + drift"
                )
            self.summary_label.setText(text)
            if result.warnings:
                self.diagnostics.setPlainText("\n".join(result.warnings[:1000]))
                if len(result.warnings) > 1000:
                    self.diagnostics.appendPlainText(
                        f"… {len(result.warnings) - 1000:,} more diagnostics"
                    )
            self.status.setText(f"Compared {sum(len(t.rows) for _, t in sources):,} source rows.")
            self._sync_detail_presentation()
            if result.warnings:
                self.feedback_panel.setCurrentWidget(self.diagnostics)
                self.feedback_toggle.setChecked(True)
            if self.height() < 600:
                self.results_host.show()
                self._collapse_setup()

        self.submit("Comparing tables", compare, complete)

    def _display_option_changed(self) -> None:
        if self.result is not None:
            status = self.status_filter.currentData()
            identical = "identical" if self.result.two_way else "ok"
            if not self.show_identical.isChecked() and status == identical:
                self.show_identical.setChecked(True)
            self.result_model.set_result(self.result, self.show_identical.isChecked())
            self._schedule_filter()

    def _status_filter_changed(self, *_args) -> None:
        identical = "identical" if self.result and self.result.two_way else "ok"
        if self.status_filter.currentData() == identical and not self.show_identical.isChecked():
            self.show_identical.setChecked(True)
        self._schedule_filter()

    def _schedule_filter(self, *_args) -> None:
        if self.result is not None:
            self._filter_timer.start()

    def _apply_filter(self) -> None:
        result = self.result
        revision = self.input_revision
        if result is None:
            return
        query = self.search.text().casefold()
        status = self.status_filter.currentData()
        identical = "identical" if result.two_way else "ok"
        candidate = tuple(
            index for index, row in enumerate(result.rows)
            if self.show_identical.isChecked() or row.status != identical
        )
        self.result_view.setEnabled(False)

        def filter_rows(context):
            visible = []
            for position, row_index in enumerate(candidate):
                if position % 2048 == 0:
                    context.check_cancelled()
                row = result.rows[row_index]
                if status != "all" and row.status != status:
                    continue
                if query:
                    values = [logic.format_cell(row.key), row.status]
                    values.extend(result.columns[index] for index in row.diff_columns)
                    for source_index, source_row in enumerate(row.source_rows):
                        if source_row is not None:
                            table = result.sources[source_index][1]
                            values.extend(
                                table.rows[source_row][table.column_index[col]] or ""
                                for col in result.columns
                            )
                    if query not in " ".join(values).casefold():
                        continue
                visible.append(row_index)
            return visible

        def complete(visible):
            self.result_view.setEnabled(True)
            if revision == self.input_revision and self.result is result and isinstance(visible, list):
                self.result_model.set_visible(visible)

        self.submit("Filtering comparison", filter_rows, complete)

    def _sort_requested(self, column: int, order) -> None:
        result = self.result
        if result is None:
            return
        revision = self.input_revision
        ascending = order == Qt.SortOrder.AscendingOrder
        column_name = self.result_model.headers[column]
        candidate = tuple(self.result_model.visible)

        def sort_rows(context):
            def value(index):
                row = result.rows[index]
                if column_name == "Status":
                    return row.status
                if column_name == result.key_column:
                    return (row.key is not None, row.key or "")
                if column_name == "Present":
                    return row.present_count
                if column_name == "Match":
                    return row.match_count
                if column_name == "Differing columns":
                    return tuple(result.columns[i] for i in row.diff_columns)
                if column_name not in result.columns:
                    return ""
                source = 0 if result.two_way else next(
                    (i for i, row_offset in enumerate(row.source_rows) if row_offset is not None), 0
                )
                row_offset = row.source_rows[source]
                return "" if row_offset is None else (
                    result.sources[source][1].rows[row_offset][
                        result.sources[source][1].column_index[column_name]
                    ] or ""
                )

            return sorted(candidate, key=value, reverse=not ascending)

        def complete(indices):
            if revision == self.input_revision and self.result is result and isinstance(indices, list):
                self.result_model.set_visible(indices)

        self.submit("Sorting comparison", sort_rows, complete)

    def _selected_result_row(self) -> int | None:
        if self.result is None:
            return None
        selection = self.result_view.selectionModel().selectedRows()
        return selection[0].data(Qt.ItemDataRole.UserRole) if selection else None

    def _selection_changed(self, *_args) -> None:
        self._detail_dismissed = False
        self._fill_detail()
        self._sync_detail_presentation()

    def _fill_detail(self) -> None:
        row_index = self._selected_result_row()
        if row_index is None:
            self.detail_model.set_values((), ())
            return
        row = self.result.rows[row_index]
        positions = [self.result.columns.index(self.result.key_column)]
        positions.extend(position for position in row.diff_columns if position not in positions)
        columns = tuple(self.result.columns[i] for i in positions)
        detail_rows = []
        for source_index, (label, table) in enumerate(self.result.sources):
            offset = row.source_rows[source_index]
            if offset is None:
                detail_rows.append((label, *("— absent —" for _ in columns)))
            else:
                detail_rows.append((
                    label,
                    *(_cell_text(table.rows[offset][table.column_index[column]]) for column in columns),
                ))
        self.detail_model.set_values(("Source", *columns), tuple(detail_rows))

    def _sync_detail_presentation(self) -> None:
        """Show the selected row inline when the page is tall, in a dialog otherwise."""
        has_row = self._selected_result_row() is not None
        if not has_row:
            self._clear_detail()
            return
        if not self.detail_model.rowCount():
            self._fill_detail()
        inline = self.height() >= 820 and not self._detail_dismissed
        self.details_row.setVisible(inline)
        self.detail_view.setVisible(inline)
        self.details_button.setVisible(not inline)
        self.details_button.setEnabled(not self._busy)

    def _clear_detail(self) -> None:
        self._detail_dismissed = False
        self.detail_model.set_values((), ())
        self.details_row.hide()
        self.detail_view.hide()
        self.details_button.hide()
        self.details_button.setEnabled(False)

    def _dismiss_detail(self) -> None:
        self._detail_dismissed = True
        self._sync_detail_presentation()

    def _show_detail_dialog(self) -> None:
        if not self.detail_model.rowCount():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Selected row details")
        dialog.resize(760, 320)
        layout = QVBoxLayout(dialog)
        view = QTableView(dialog)
        view.setModel(self.detail_model)
        view.horizontalHeader().setStretchLastSection(True)
        view.verticalHeader().hide()
        layout.addWidget(view)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _export(self) -> None:
        result = self.result
        if result is None:
            return
        default = f"{datetime.now():%Y%m%d} table_comparison.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export comparison", default, "Excel workbook (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        def export(context):
            parent = Path(path).resolve().parent
            parent.mkdir(parents=True, exist_ok=True)

            def operation(stage, job):
                from logic.table_comparator import export_compact_multi_to_excel
                job.report("Writing Excel workbook")
                export_compact_multi_to_excel(
                    result,
                    str(stage / Path(path).name),
                    check_cancelled=job.check_cancelled,
                )
                return FeatureOutcome("Excel comparison workbook is ready.")

            return prepare_file_run(context, parent, operation)

        revision = self.input_revision

        def complete(outcome):
            if revision == self.input_revision and isinstance(outcome, FeatureOutcome):
                self.set_outcome(outcome)

        self.submit("Exporting comparison", export, complete)

    def _copy_summary(self) -> None:
        if not self.result:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.summary_label.text())
        self.status.setText("Summary copied.")
