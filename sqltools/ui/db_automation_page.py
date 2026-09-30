from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QPushButton, QSpinBox

from sqltools.services import run_db_automation
from sqltools.ui.base import FeaturePage
from sqltools.ui.widgets import SourceModePanel, form_layout, path_row, run_button, sql_editor


class DbAutomationPage(FeaturePage):
    def __init__(self, parent=None):
        super().__init__(
            "DB Automation Converter",
            "Format procedures, functions, and triggers for database automation.",
            parent,
        )
        source_panel, options_panel = self.add_two_column_layout()
        self.source_section, source = self.add_group("Source", source_panel)
        self.mode = SourceModePanel()
        self.editor = sql_editor(
            "Paste one or more CREATE PROCEDURE, FUNCTION, or TRIGGER statements.", 220
        )
        self.input_row, self.input_folder = path_row(
            self, "Input folder", directory=True, key="automation-input"
        )
        self.mode.addMode("Paste SQL", "paste", self.editor)
        self.mode.addMode("Input folder", "folder", self.input_row)
        source.addWidget(self.mode)

        self.options_section, options = self.add_group("Output and options", options_panel)
        self.output_row, self.output_folder = path_row(
            self, "Output folder", directory=True, key="automation-output"
        )
        options.addWidget(self.output_row)
        form = form_layout(options)
        self.sequence = QSpinBox()
        self.sequence.setRange(1, 999999)
        self.sequence.setValue(1)
        self.developer = QLineEdit()
        self.developer.setPlaceholderText("Optional")
        self.description = QLineEdit()
        self.description.setPlaceholderText("Optional")
        form.addRow("Starting sequence", self.sequence)
        form.addRow("Developer", self.developer)
        form.addRow("Description", self.description)
        execute = run_button("Convert")
        clear = QPushButton("Clear")
        execute.clicked.connect(self._execute)
        clear.clicked.connect(self._clear)
        self.add_actions(execute, clear)
        self.finish_inputs()

    def _execute(self) -> None:
        output = self.output_folder.text().strip()
        mode = self.mode.currentData()
        paste = self.editor.toPlainText() if mode == "paste" else ""
        input_folder = self.input_folder.text().strip() if mode == "folder" else ""
        if not output:
            self.set_field_error(self.output_folder, "Choose an output folder.")
            return
        if mode == "paste" and not paste.strip():
            self.set_field_error(self.editor, "Paste at least one database object definition.")
            return
        if mode == "folder" and not input_folder:
            self.set_field_error(self.input_folder, "Choose an input folder.")
            return
        request = {
            "mode": mode,
            "paste": paste,
            "input_folder": input_folder,
            "output_folder": output,
            "sequence": self.sequence.value(),
            "developer": self.developer.text().strip(),
            "description": self.description.text().strip(),
        }
        self.reset_output()
        self.submit(
            "Converting database objects", lambda context: run_db_automation(context, request)
        )

    def _clear(self) -> None:
        self.editor.clear()
        self.input_folder.clear()
        self.output_folder.clear()
        self.sequence.setValue(1)
        self.developer.clear()
        self.description.clear()
        self.mode.setCurrentIndex(0)
        self.reset_output()
