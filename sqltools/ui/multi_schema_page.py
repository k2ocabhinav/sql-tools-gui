from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from logic.multi_schema_combiner import DEFAULT_SCHEMAS
from sqltools.services import run_multi_schema
from sqltools.ui.base import FeaturePage
from sqltools.ui.widgets import (
    CheckBox,
    SourceModePanel,
    form_layout,
    path_row,
    run_button,
    source_file_picker_panel,
    sql_editor,
)


class MultiSchemaPage(FeaturePage):
    def __init__(self, parent=None):
        super().__init__(
            "Multi-Schema Combiner",
            "Produce one ordered deployment file for the selected schemas.",
            parent,
        )
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.content_grid_widget = QWidget()
        self.content_grid = QGridLayout()
        self.content_grid.setContentsMargins(0, 0, 0, 0)
        self.content_grid.setHorizontalSpacing(10)
        self.content_grid.setVerticalSpacing(8)
        self.content_grid_widget.setLayout(self.content_grid)
        self.input_layout.addWidget(self.content_grid_widget)
        self.content_grid.setColumnStretch(0, 2)
        self.content_grid.setColumnStretch(1, 1)

        self.source_section, source = self.add_group("Source", self.content_grid, row=0, column=0)
        self.mode = SourceModePanel()
        self.editor = sql_editor("Paste one or more SQL workfiles.", 220)
        self.file_row, self.file_edit = source_file_picker_panel(self, "Select SQL workfiles")
        self.input_row, self.input_folder = path_row(
            self, "Input folder", directory=True, key="multi-input"
        )
        self.mode.addMode("Paste SQL", "paste", self.editor)
        self.mode.addMode("Select files", "files", self.file_row)
        self.mode.addMode("Input folder", "folder", self.input_row)
        source.addWidget(self.mode)
        source.setAlignment(self.mode, Qt.AlignmentFlag.AlignTop)
        self.mode.currentIndexChanged.connect(self._toggle_mode)

        self.schemas_section, schemas_group = self.add_group(
            "Target schemas", self.content_grid, row=0, column=1
        )
        selection_row = QWidget()
        selection_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        selection_layout = QHBoxLayout(selection_row)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        all_button = QPushButton("All")
        none_button = QPushButton("None")
        self.schema_summary = QLabel()
        self.schema_summary.setObjectName("muted")
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button.clicked.connect(lambda: self._set_all(False))
        selection_layout.addWidget(self.schema_summary, 1)
        selection_layout.addWidget(all_button)
        selection_layout.addWidget(none_button)
        schemas_group.addWidget(selection_row)

        self.schema_checks: dict[str, CheckBox] = {}
        self.schema_grid = QGridLayout()
        self.schema_grid.setContentsMargins(0, 2, 0, 2)
        self.schema_grid.setHorizontalSpacing(12)
        self.schema_grid.setVerticalSpacing(3)
        schemas_group.addLayout(self.schema_grid)
        schemas_group.setAlignment(self.schema_grid, Qt.AlignmentFlag.AlignTop)
        for schema in DEFAULT_SCHEMAS:
            self._insert_schema(schema)

        custom_row = QWidget()
        custom_layout = QHBoxLayout(custom_row)
        custom_layout.setContentsMargins(0, 4, 0, 0)
        self.custom_schema = QLineEdit()
        self.custom_schema.setPlaceholderText("Add a custom schema")
        add_schema = QPushButton("Add")
        add_schema.clicked.connect(self._add_schema)
        self.custom_schema.returnPressed.connect(self._add_schema)
        custom_layout.addWidget(self.custom_schema, 1)
        custom_layout.addWidget(add_schema)
        self.custom_row = custom_row
        self._place_custom_row()
        self.schema_error = QLabel()
        self.schema_error.setObjectName("fieldError")
        self.schema_error.hide()
        schemas_group.addWidget(self.schema_error)

        self.output_section, output = self.add_group("Output", self.input_layout)
        self.output_row, self.output_folder = path_row(
            self, "Output folder", directory=True, key="multi-output"
        )
        output.addWidget(self.output_row)
        form = form_layout(output)
        self.filename = QLineEdit(f"{datetime.now():%Y%m%d} Multi-Schema Combined.sql")
        form.addRow("Filename", self.filename)
        self.input_layout.addStretch(1)
        self._update_schema_summary()

        execute = run_button("Combine and save")
        copy = QPushButton("Combine and copy")
        clear = QPushButton("Clear")
        execute.clicked.connect(lambda: self._execute(False))
        copy.clicked.connect(lambda: self._execute(True))
        clear.clicked.connect(self._clear)
        self.add_actions(execute, copy, clear)
        self.source_content = source
        self._toggle_mode()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "output_section"):
            self._reflow_sections(self.width() < 680)

    def _reflow_sections(self, stacked: bool) -> None:
        if getattr(self, "_is_stacked_layout", None) == stacked:
            return
        self._is_stacked_layout = stacked
        self.content_grid.removeWidget(self.source_section)
        self.content_grid.removeWidget(self.schemas_section)
        if stacked:
            self.content_grid.addWidget(self.source_section, 0, 0, 1, 2)
            self.content_grid.addWidget(self.schemas_section, 1, 0, 1, 2)
        else:
            self.content_grid.addWidget(self.source_section, 0, 0)
            self.content_grid.addWidget(self.schemas_section, 0, 1)
        self.content_grid.setRowStretch(0, 1 if self.mode.currentData() == "paste" else 0)
        self.content_grid.setRowStretch(1, 0)

    def _toggle_mode(self, *_args) -> None:
        mode = self.mode.currentData()
        self.source_content.setStretch(0, 1 if mode == "paste" else 0)
        self.content_grid.setRowStretch(0, 1 if mode == "paste" else 0)
        self.input_layout.setStretch(
            self.input_layout.indexOf(self.content_grid_widget), 1 if mode == "paste" else 0
        )
        self._reflow_sections(self.width() < 680)

    def _insert_schema(self, name: str) -> None:
        check = CheckBox(name)
        check.setChecked(True)
        check.toggled.connect(self._update_schema_summary)
        self.schema_checks[name] = check
        position = len(self.schema_checks) - 1
        self.schema_grid.addWidget(check, position // 2, position % 2)
        self._place_custom_row()

    def _place_custom_row(self) -> None:
        if not hasattr(self, "custom_row"):
            return
        self.schema_grid.removeWidget(self.custom_row)
        row = (len(self.schema_checks) + 1) // 2
        self.schema_grid.addWidget(self.custom_row, row, 0, 1, 2)

    def _add_schema(self) -> None:
        value = self.custom_schema.text().strip()
        if not value:
            self.custom_schema.setFocus()
            return
        if value in self.schema_checks:
            self.schema_checks[value].setChecked(True)
        else:
            self._insert_schema(value)
        self.custom_schema.clear()
        self._update_schema_summary()

    def _set_all(self, enabled: bool) -> None:
        for check in self.schema_checks.values():
            check.setChecked(enabled)

    def _update_schema_summary(self, *_args) -> None:
        selected = sum(check.isChecked() for check in self.schema_checks.values())
        self.schema_summary.setText(f"{selected} of {len(self.schema_checks)} selected")
        if selected:
            self.schema_error.clear()
            self.schema_error.hide()

    def _execute(self, copy: bool) -> None:
        mode = self.mode.currentData()
        paste = self.editor.toPlainText() if mode == "paste" else ""
        files = self.file_edit.paths() if mode == "files" else []
        input_folder = self.input_folder.text().strip() if mode == "folder" else ""
        schemas = [name for name, box in self.schema_checks.items() if box.isChecked()]
        if not schemas:
            self.schema_error.setText("Select at least one target schema.")
            self.schema_error.show()
            next(iter(self.schema_checks.values())).setFocus()
            self._set_status("Select at least one target schema.", "failed")
            return
        if mode == "paste" and not paste.strip():
            self.set_field_error(self.editor, "Paste the SQL workfiles you want to combine.")
            return
        if mode == "files" and not files:
            self.set_field_error(self.file_edit, "Select one or more SQL workfiles.")
            self.file_edit.add_button.setFocus()
            return
        if mode == "folder" and not input_folder:
            self.set_field_error(self.input_folder, "Choose an input folder.")
            return
        if not copy and not self.output_folder.text().strip():
            self.set_field_error(self.output_folder, "Choose an output folder.")
            return
        request = {
            "mode": mode,
            "paste": paste,
            "files": files,
            "input_folder": input_folder,
            "schemas": schemas,
            "output_folder": self.output_folder.text().strip(),
            "filename": self.filename.text().strip(),
            "copy": copy,
        }
        self.reset_output()
        label = "Combining schemas" if copy else "Combining schemas for file output"
        self.submit(label, lambda context: run_multi_schema(context, request))

    def _clear(self) -> None:
        self.editor.clear()
        self.file_edit.clear()
        self.input_folder.clear()
        self.output_folder.clear()
        self.mode.setCurrentIndex(0)
        self._set_all(True)
        self._toggle_mode()
        self.reset_output()
