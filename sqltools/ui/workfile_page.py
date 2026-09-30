from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QLineEdit,
    QPushButton,
)

from logic.private_defaults import default_developer_name, default_temp_prefix
from sqltools.services import run_workfile
from sqltools.ui.base import FeaturePage
from sqltools.ui.widgets import CheckBox, labeled_field, path_row, run_button, sql_editor


class WorkfilePage(FeaturePage):
    def __init__(self, parent=None):
        super().__init__(
            "Workfile Generator",
            "Create versioned SQL workfiles with JIRA folders and backups.",
            parent,
        )
        self.source_section, source = self.add_group("SQL object")
        self.editor = sql_editor(
            "Paste one or more CREATE procedure, function, trigger, or view statements.", 240
        )
        self.editor.setObjectName("workfileSqlEditor")
        source.addWidget(self.editor)

        self.options_section, options = self.add_group("Workfile options")
        self.base_row, self.base_folder = path_row(
            self, "Base folder", directory=True, key="workfile-base"
        )
        options.addWidget(self.base_row)

        settings_grid = QGridLayout()
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(16)
        settings_grid.setVerticalSpacing(8)
        settings_grid.setColumnStretch(0, 1)
        settings_grid.setColumnStretch(1, 1)

        self.jira = QLineEdit()
        self.jira.setPlaceholderText("Ticket number")
        self.create_folder = CheckBox("Create or use JIRA folder")
        self.create_folder.setChecked(True)
        self.description = QLineEdit()
        self.developer = QLineEdit(default_developer_name())
        self.temp_prefix = QLineEdit(default_temp_prefix())

        settings_grid.addWidget(
            labeled_field("JIRA number", self.jira), 0, 0, alignment=Qt.AlignmentFlag.AlignTop
        )
        settings_grid.addWidget(
            labeled_field("Description", self.description),
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        settings_grid.addWidget(
            self.create_folder,
            1,
            0,
            1,
            2,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        settings_grid.addWidget(
            labeled_field("Developer", self.developer), 2, 0, alignment=Qt.AlignmentFlag.AlignTop
        )
        settings_grid.addWidget(
            labeled_field("Temporary prefix", self.temp_prefix),
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        options.addLayout(settings_grid)

        execute = run_button("Generate files")
        copy = QPushButton("Generate and copy")
        clear = QPushButton("Clear")
        execute.clicked.connect(lambda: self._execute(False))
        copy.clicked.connect(lambda: self._execute(True))
        clear.clicked.connect(self._clear)
        self.add_actions(execute, copy, clear)
        self.finish_inputs()

    def _execute(self, copy: bool) -> None:
        paste = self.editor.toPlainText()
        if not paste.strip():
            self.set_field_error(
                self.editor, "Paste the SQL object you want to turn into a workfile."
            )
            return
        if not copy and not self.base_folder.text().strip():
            self.set_field_error(self.base_folder, "Choose a base folder for file output.")
            return
        if self.create_folder.isChecked() and not self.jira.text().strip():
            self.set_field_error(self.jira, "Enter a JIRA number when creating a JIRA folder.")
            return
        request = {
            "paste": paste,
            "jira": self.jira.text().strip(),
            "base_folder": self.base_folder.text().strip(),
            "developer": self.developer.text().strip(),
            "temp_prefix": self.temp_prefix.text().strip(),
            "description": self.description.text().strip(),
            "create_jira_folder": self.create_folder.isChecked(),
            "copy": copy,
        }
        self.reset_output()
        label = "Preparing SQL for clipboard" if copy else "Generating versioned workfiles"
        self.submit(label, lambda context: run_workfile(context, request))

    def _clear(self) -> None:
        self.editor.clear()
        self.jira.clear()
        self.description.clear()
        self.base_folder.clear()
        self.create_folder.setChecked(True)
        self.reset_output()
