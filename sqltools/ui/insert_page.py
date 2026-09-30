from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QLineEdit, QPushButton

from sqltools.services import run_insert
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


class InsertPage(FeaturePage):
    def __init__(self, parent=None):
        super().__init__(
            "INSERT Consolidator",
            "Combine MySQL Workbench INSERT exports and prepare release files.",
            parent,
        )
        source_panel, options_panel = self.add_two_column_layout()
        self.source_section, source = self.add_group("Source", source_panel)
        self.mode = SourceModePanel()
        self.editor = sql_editor("Paste INSERT export blocks.", 220)
        self.files_row, self.files_edit = source_file_picker_panel(self, "Select INSERT SQL files")
        self.input_row, self.input_folder = path_row(
            self, "Input folder", directory=True, key="insert-input"
        )
        self.mode.addMode("Paste SQL", "paste", self.editor)
        self.mode.addMode("Select files", "files", self.files_row)
        self.mode.addMode("Input folder", "folder", self.input_row)
        source.addWidget(self.mode)

        self.options_section, options = self.add_group("Output and options", options_panel)
        self.output_row, self.output_folder = path_row(
            self, "Output folder", directory=True, key="insert-output"
        )
        options.addWidget(self.output_row)
        form = form_layout(options)
        self.date_prefix = QLineEdit(datetime.now().strftime("%Y%m%d"))
        form.addRow("Date prefix", self.date_prefix)
        self.modify_in_place = CheckBox("Modify files in place")
        self.modify_in_place.setEnabled(False)
        self.combined = CheckBox("Create combined SQL file")
        self.excel = CheckBox("Create Excel count summary")
        self.excel.setChecked(True)
        form.addRow("", self.modify_in_place)
        form.addRow("", self.combined)
        form.addRow("", self.excel)
        self.mode.currentIndexChanged.connect(self._toggle_mode)
        self._toggle_mode()

        execute = run_button("Consolidate")
        clear = QPushButton("Clear")
        execute.clicked.connect(self._execute)
        clear.clicked.connect(self._clear)
        self.add_actions(execute, clear)
        self.finish_inputs()

    def _toggle_mode(self, *_args) -> None:
        self.modify_in_place.setEnabled(self.mode.currentData() == "folder")

    def _execute(self) -> None:
        mode = self.mode.currentData()
        paste = self.editor.toPlainText() if mode == "paste" else ""
        files = self.files_edit.paths() if mode == "files" else []
        source_folder = self.input_folder.text().strip() if mode == "folder" else ""
        destination = (
            source_folder
            if source_folder and self.modify_in_place.isChecked()
            else (self.output_folder.text().strip())
        )
        if not destination:
            self.set_field_error(self.output_folder, "Choose an output folder.")
            return
        if mode == "paste" and not paste.strip():
            self.set_field_error(
                self.editor, "Paste the INSERT statements you want to consolidate."
            )
            return
        if mode == "files" and not files:
            self.set_field_error(self.files_edit, "Select one or more SQL files.")
            self.files_edit.add_button.setFocus()
            return
        if mode == "folder" and not source_folder:
            self.set_field_error(self.input_folder, "Choose an input folder.")
            return
        request = {
            "paste": paste,
            "files": files,
            "input_folder": source_folder,
            "output_folder": destination,
            "date_prefix": self.date_prefix.text().strip(),
            "generate_combined": self.combined.isChecked(),
            "excel": self.excel.isChecked(),
        }
        self.reset_output()
        self.submit("Consolidating INSERT files", lambda context: run_insert(context, request))

    def _clear(self) -> None:
        self.editor.clear()
        self.files_edit.clear()
        self.input_folder.clear()
        self.output_folder.clear()
        self.mode.setCurrentIndex(0)
        self.modify_in_place.setChecked(False)
        self.combined.setChecked(False)
        self.excel.setChecked(True)
        self._toggle_mode()
        self.reset_output()
