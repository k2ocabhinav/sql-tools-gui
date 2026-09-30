from __future__ import annotations

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QSettings, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QPushButton,
    QWidget,
)

from logic import table_comparator as tc
from sqltools.app import MainWindow
from sqltools.theme import COLORS, _ui_font, apply_theme
from sqltools.ui.db_automation_page import DbAutomationPage
from sqltools.ui.insert_page import InsertPage
from sqltools.ui.multi_schema_page import MultiSchemaPage
from sqltools.ui.table_compare_page import TableComparePage
from sqltools.ui.workfile_page import WorkfilePage


def test_navigation_starts_under_brand_and_remains_in_tool_order(qtbot):
    window = MainWindow(["INSERT_CONSOLIDATOR", "DB_AUTOMATION", "WORKFILE_GENERATOR"])
    qtbot.addWidget(window)
    window.resize(1240, 790)
    window.show()
    qtbot.wait(20)

    # Find the static label by object name without depending on the concrete font platform.
    from PySide6.QtWidgets import QLabel

    brand = window.sidebar.findChild(QLabel, "brand")
    assert brand is not None
    assert (
        window.nav_buttons[0].mapTo(window.sidebar, window.nav_buttons[0].rect().topLeft()).y()
        < brand.geometry().bottom() + 80
    )
    ys = [
        button.mapTo(window.sidebar, button.rect().topLeft()).y() for button in window.nav_buttons
    ]
    assert ys == sorted(ys)
    assert all(button.isVisible() for button in window.nav_buttons)
    qtbot.mouseClick(window.nav_buttons[1], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 1
    assert [button.isChecked() for button in window.nav_buttons] == [False, True, False]


def test_reduce_motion_disables_transitions_and_persists(qtbot, monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        "sqltools.app.QSettings",
        lambda: QSettings(str(settings_path), QSettings.Format.IniFormat),
    )
    window = MainWindow(["INSERT_CONSOLIDATOR", "DB_AUTOMATION", "WORKFILE_GENERATOR"])
    qtbot.addWidget(window)
    window.resize(1240, 790)
    window.show()
    qtbot.wait(20)

    window.reduce_motion_action.setChecked(True)
    page = window.pages[0]
    page.feedback_toggle.click()
    assert page.feedback_panel.isVisible()
    assert page.feedback_panel.maximumHeight() == page._feedback_height
    assert page._feedback_animation.state() == QAbstractAnimation.State.Stopped

    window.nav_buttons[1].click()
    point = window.nav_buttons[1].mapTo(window.sidebar, QPoint(0, 0))
    assert window.stack.currentIndex() == 1
    assert window.nav_marker.geometry() == QRect(
        4, point.y() + 4, 3, max(20, window.nav_buttons[1].height() - 8)
    )
    assert window.nav_marker_animation.state() == QAbstractAnimation.State.Stopped

    window.settings.sync()
    stored_settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    assert stored_settings.value("view/reduce_motion", False, type=bool)


def test_ui_uses_native_platform_font_families(qtbot):
    general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    page = MultiSchemaPage()
    qtbot.addWidget(page)

    assert _ui_font().family() == general.family()
    assert page.editor.font().family() == fixed.family()


def test_theme_text_and_control_boundaries_meet_contrast_targets():
    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return sum(
            weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear, strict=True)
        )

    def ratio(foreground: str, background: str) -> float:
        lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    assert ratio(COLORS["text"], COLORS["workspace"]) >= 4.5
    assert ratio(COLORS["muted"], COLORS["workspace"]) >= 4.5
    assert ratio(COLORS["sidebar_text"], COLORS["sidebar"]) >= 4.5
    assert ratio("#FFFFFF", COLORS["accent"]) >= 4.5
    assert ratio(COLORS["accent"], COLORS["input"]) >= 3.0
    assert ratio(COLORS["border"], COLORS["input"]) >= 3.0


def test_disabled_primary_button_uses_neutral_surface(qtbot):
    app = QApplication.instance()
    assert app is not None
    apply_theme(app)
    button = QPushButton("Compare")
    button.setObjectName("primary")
    button.setEnabled(False)
    button.resize(160, 40)
    qtbot.addWidget(button)
    button.show()
    qtbot.wait(10)

    image = button.grab().toImage()
    background = image.pixelColor(image.width() // 2, image.height() // 4)
    assert background.name().lower() == COLORS["surface"].lower()


def test_multi_schema_reflows_without_losing_input_or_selection(qtbot):
    page = MultiSchemaPage()
    qtbot.addWidget(page)
    page.resize(1240, 720)
    page.show()
    page.editor.setPlainText("USE schema_a;\nSELECT 1;")
    first_schema = next(iter(page.schema_checks.values()))
    first_schema.setChecked(False)
    qtbot.wait(20)

    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.source_section))[
        :2
    ] == (0, 0)
    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.schemas_section))[
        :2
    ] == (0, 1)
    assert all(box.isChecked() for box in page.schema_checks.values()) is False
    assert not first_schema.isChecked()

    page.resize(600, 500)
    qtbot.wait(20)
    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.source_section))[
        :2
    ] == (0, 0)
    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.schemas_section))[
        :2
    ] == (1, 0)
    assert page.editor.toPlainText() == "USE schema_a;\nSELECT 1;"
    assert not first_schema.isChecked()


@pytest.mark.parametrize(
    ("page_type", "modes"),
    [
        (InsertPage, ("paste", "files", "folder")),
        (DbAutomationPage, ("paste", "folder")),
        (MultiSchemaPage, ("paste", "files", "folder")),
    ],
)
def test_source_modes_keep_controls_aligned_and_sections_close(page_type, modes, qtbot, tmp_path):
    page = page_type()
    qtbot.addWidget(page)
    page.resize(620, 680)
    page.show()
    qtbot.wait(20)

    page.editor.setPlainText("CREATE PROCEDURE sample() SELECT 1;")
    if hasattr(page, "files_edit"):
        page.files_edit.add_paths([str(tmp_path / "sample.sql")])
    if hasattr(page, "file_edit"):
        page.file_edit.add_paths([str(tmp_path / "sample.sql")])
    page.input_folder.setText(str(tmp_path))

    columns = page.findChild(QWidget, "responsiveColumns")
    if columns is not None:
        assert columns.grid.getItemPosition(columns.grid.indexOf(columns.panels[0]))[:2] == (0, 0)
        assert columns.grid.getItemPosition(columns.grid.indexOf(columns.panels[1]))[:2] == (1, 0)

    for index, mode_name in enumerate(modes):
        # Exercise the same clicked signal path used by a person in the app. A
        # programmatic setCurrentIndex alone would miss broken selector wiring.
        qtbot.mouseClick(page.mode.switch._buttons.button(index), Qt.MouseButton.LeftButton)
        qtbot.wait(10)

        assert page.mode.currentIndex() == index
        assert page.mode.content.currentIndex() == index
        assert page.mode.content.currentWidget().objectName() == "sourceModeSlot"

        switch_top = page.mode.switch.mapTo(page, QPoint(0, 0)).y()
        content_top = page.mode.content.mapTo(page, QPoint(0, 0)).y()
        assert content_top - (switch_top + page.mode.switch.height()) <= 12
        assert (
            page.mode.switch.mapTo(page, QPoint(0, 0)).x()
            == page.mode.content.mapTo(page, QPoint(0, 0)).x()
        )
        assert page.mode.switch.width() == page.mode.switch.sizeHint().width()
        assert page.mode.switch.width() < page.mode.width()
        assert (
            page.mode.content.sizeHint().height()
            >= page.mode.content.currentWidget().minimumHeight()
        )
        assert page.mode.content.currentWidget().isVisible()

        input_widget = {
            "paste": page.editor,
            "files": getattr(page, "files_row", getattr(page, "file_row", None)),
            "folder": page.input_row,
        }[mode_name]
        assert input_widget is not None
        assert input_widget.mapTo(page.mode.content, QPoint(0, 0)).x() == 0
        assert input_widget.mapTo(page.mode.content, QPoint(0, 0)).y() <= 2
        assert input_widget.width() == page.mode.content.width()
        if isinstance(page, InsertPage):
            assert page.modify_in_place.isEnabled() is (mode_name == "folder")

        if hasattr(page, "options_section"):
            section_gap = page.options_section.mapTo(page, QPoint(0, 0)).y() - (
                page.source_section.mapTo(page, QPoint(0, 0)).y() + page.source_section.height()
            )
            assert 8 <= section_gap <= 24

        if mode_name == "paste":
            assert page.editor.toPlainText() == "CREATE PROCEDURE sample() SELECT 1;"
        elif mode_name == "files":
            picker = getattr(page, "files_edit", getattr(page, "file_edit", None))
            assert picker is not None
            assert picker.paths() == [str(tmp_path / "sample.sql")]
        else:
            assert page.input_folder.text() == str(tmp_path)

    page.resize(1100, 760)
    qtbot.wait(20)
    assert page.mode.switch.width() == page.mode.switch.sizeHint().width()
    assert page.mode.switch.width() < page.mode.width()
    if columns is not None:
        assert columns.grid.getItemPosition(columns.grid.indexOf(columns.panels[1]))[:2] == (0, 1)
        assert (
            page.source_section.mapTo(page, QPoint(0, 0)).y()
            == page.options_section.mapTo(page, QPoint(0, 0)).y()
        )


@pytest.mark.parametrize(
    ("page_type", "modes", "service_path"),
    [
        (InsertPage, ("paste", "files", "folder"), "sqltools.ui.insert_page.run_insert"),
        (
            DbAutomationPage,
            ("paste", "folder"),
            "sqltools.ui.db_automation_page.run_db_automation",
        ),
        (
            MultiSchemaPage,
            ("paste", "files", "folder"),
            "sqltools.ui.multi_schema_page.run_multi_schema",
        ),
    ],
)
def test_source_modes_route_the_selected_value_to_the_operation(
    page_type, modes, service_path, monkeypatch, qtbot, tmp_path
):
    source_path = tmp_path / "sample.sql"
    source_path.write_text("SELECT 1;\n", encoding="utf-8")
    input_folder = tmp_path / "input"
    input_folder.mkdir()
    output_folder = tmp_path / "output"
    captured_requests = []
    queued_operations = []
    monkeypatch.setattr(
        service_path,
        lambda _context, request: captured_requests.append(dict(request)),
    )

    page = page_type()
    qtbot.addWidget(page)
    page.editor.setPlainText("SELECT 1;\n")
    page.output_folder.setText(str(output_folder))
    page.input_folder.setText(str(input_folder))
    if hasattr(page, "files_edit"):
        page.files_edit.add_paths([str(source_path)])
    if hasattr(page, "file_edit"):
        page.file_edit.add_paths([str(source_path)])
    page.request_job.connect(
        lambda _name, operation, _on_finished: queued_operations.append(operation)
    )

    for index, mode_name in enumerate(modes):
        page.mode.setCurrentIndex(index)
        if page_type is MultiSchemaPage:
            page._execute(False)
        else:
            page._execute()
        queued_operations[-1](None)
        request = captured_requests[-1]

        assert request.get("paste", "") == ("SELECT 1;\n" if mode_name == "paste" else "")
        if page_type in (InsertPage, MultiSchemaPage):
            assert request["files"] == ([str(source_path)] if mode_name == "files" else [])
            assert request["input_folder"] == (str(input_folder) if mode_name == "folder" else "")
        elif page_type is DbAutomationPage:
            assert request["mode"] == mode_name
            assert request["input_folder"] == (str(input_folder) if mode_name == "folder" else "")


@pytest.mark.parametrize("copy", [False, True])
def test_workfile_paste_and_metadata_route_to_generation_job(monkeypatch, qtbot, tmp_path, copy):
    captured_requests = []
    queued_operations = []
    monkeypatch.setattr(
        "sqltools.ui.workfile_page.run_workfile",
        lambda _context, request: captured_requests.append(dict(request)),
    )
    page = WorkfilePage()
    qtbot.addWidget(page)
    page.editor.setPlainText("CREATE PROCEDURE sample() SELECT 1;")
    page.base_folder.setText(str(tmp_path))
    page.jira.setText("DB-1234")
    page.description.setText("Sample deployment")
    page.request_job.connect(
        lambda _name, operation, _on_finished: queued_operations.append(operation)
    )

    page._execute(copy)
    queued_operations[-1](None)

    request = captured_requests[0]
    assert request["paste"] == "CREATE PROCEDURE sample() SELECT 1;"
    assert request["base_folder"] == str(tmp_path)
    assert request["jira"] == "DB-1234"
    assert request["description"] == "Sample deployment"
    assert request["copy"] is copy


def test_multi_schema_modes_reflow_without_scattered_sections(qtbot, tmp_path):
    page = MultiSchemaPage()
    qtbot.addWidget(page)
    page.resize(620, 700)
    page.show()
    page.editor.setPlainText("USE schema_a;\nSELECT 1;")
    page.file_edit.add_paths([str(tmp_path / "workfile.sql")])
    page.input_folder.setText(str(tmp_path))
    qtbot.wait(20)

    for index, mode_name in enumerate(("paste", "files", "folder")):
        qtbot.mouseClick(page.mode.switch._buttons.button(index), Qt.MouseButton.LeftButton)
        qtbot.wait(15)

        switch_bottom = page.mode.switch.mapTo(page, QPoint(0, 0)).y() + page.mode.switch.height()
        content_top = page.mode.content.mapTo(page, QPoint(0, 0)).y()
        assert content_top - switch_bottom <= 12
        assert (
            page.mode.switch.mapTo(page, QPoint(0, 0)).x()
            == page.mode.content.mapTo(page, QPoint(0, 0)).x()
        )
        assert page.mode.switch.width() == page.mode.switch.sizeHint().width()
        assert page.mode.switch.width() < page.mode.width()
        assert page.mode.content.currentWidget().isVisible()
        input_widget = (page.editor, page.file_row, page.input_row)[index]
        assert input_widget.mapTo(page.mode.content, QPoint(0, 0)).x() == 0
        assert input_widget.mapTo(page.mode.content, QPoint(0, 0)).y() <= 2
        assert input_widget.width() == page.mode.content.width()

        schemas_gap = page.schemas_section.mapTo(page, QPoint(0, 0)).y() - (
            page.source_section.mapTo(page, QPoint(0, 0)).y() + page.source_section.height()
        )
        output_gap = page.output_section.mapTo(page, QPoint(0, 0)).y() - (
            page.schemas_section.mapTo(page, QPoint(0, 0)).y() + page.schemas_section.height()
        )
        assert 4 <= schemas_gap <= 16
        assert 8 <= output_gap <= 24

        if mode_name == "paste":
            assert page.editor.toPlainText() == "USE schema_a;\nSELECT 1;"
        elif mode_name == "files":
            assert page.file_edit.paths() == [str(tmp_path / "workfile.sql")]
        else:
            assert page.input_folder.text() == str(tmp_path)

    page.resize(1240, 790)
    qtbot.wait(20)
    assert page.mode.switch.width() == page.mode.switch.sizeHint().width()
    assert page.mode.switch.width() < page.mode.width()
    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.source_section))[
        :2
    ] == (0, 0)
    assert page.content_grid.getItemPosition(page.content_grid.indexOf(page.schemas_section))[
        :2
    ] == (0, 1)
    assert (
        page.source_section.mapTo(page, QPoint(0, 0)).y()
        == page.schemas_section.mapTo(page, QPoint(0, 0)).y()
    )


def test_multi_schema_keeps_all_default_choices_visible_and_custom_order(qtbot):
    page = MultiSchemaPage()
    qtbot.addWidget(page)
    assert len(page.schema_checks) == 7
    assert all(box.isChecked() for box in page.schema_checks.values())
    page.custom_schema.setText("schema_custom_a")
    page._add_schema()
    page.custom_schema.setText("schema_custom_b")
    page._add_schema()
    assert list(page.schema_checks)[-2:] == ["schema_custom_a", "schema_custom_b"]
    page.custom_schema.setText("schema_custom_a")
    page._add_schema()
    assert len(page.schema_checks) == 9
    assert page.schema_checks["schema_custom_a"].isChecked()


def test_workfile_page_loads_local_defaults_without_public_identity(tmp_path, monkeypatch, qtbot):
    settings = tmp_path / "private.json"
    settings.write_text(
        '{"developer_name":"Local Developer","temp_prefix":"temp_local_"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(settings))
    page = WorkfilePage()
    qtbot.addWidget(page)

    assert page.developer.text() == "Local Developer"
    assert page.temp_prefix.text() == "temp_local_"


def test_workfile_sql_editor_uses_full_width_above_compact_options(qtbot):
    page = WorkfilePage()
    qtbot.addWidget(page)
    page.resize(1240, 790)
    page.show()
    qtbot.wait(20)

    assert page.editor.width() >= page.width() - 80
    assert page.editor.height() >= 240
    assert (
        page.source_section.mapTo(page, QPoint(0, 0)).y()
        < page.options_section.mapTo(page, QPoint(0, 0)).y()
    )

    page.resize(600, 500)
    qtbot.wait(20)
    assert page.editor.width() >= page.width() - 80
    assert page.editor.isVisible()
    assert page.jira.isVisible()


def test_workfile_inputs_stay_aligned_at_compact_width(qtbot, tmp_path):
    page = WorkfilePage()
    qtbot.addWidget(page)
    page.resize(620, 680)
    page.show()
    page.editor.setPlainText("CREATE PROCEDURE sample() SELECT 1;")
    page.base_folder.setText(str(tmp_path))
    page.jira.setText("DB-1234")
    page.description.setText("sample change")
    page.developer.setText("Developer")
    page.temp_prefix.setText("temp_")
    qtbot.wait(20)

    editor_bottom = page.editor.mapTo(page, QPoint(0, 0)).y() + page.editor.height()
    options_top = page.options_section.mapTo(page, QPoint(0, 0)).y()
    assert 8 <= options_top - editor_bottom <= 24
    assert page.base_row.isVisible()
    assert page.jira.isVisible() and page.description.isVisible()
    assert page.developer.isVisible() and page.temp_prefix.isVisible()
    assert (
        abs(page.jira.mapTo(page, QPoint(0, 0)).x() - page.developer.mapTo(page, QPoint(0, 0)).x())
        <= 4
    )
    assert (
        abs(
            page.description.mapTo(page, QPoint(0, 0)).x()
            - page.temp_prefix.mapTo(page, QPoint(0, 0)).x()
        )
        <= 4
    )


@pytest.mark.parametrize("size", [(620, 680), (1240, 790)])
def test_workfile_metadata_columns_align_labels_across_rows(qtbot, size):
    page = WorkfilePage()
    qtbot.addWidget(page)
    page.resize(*size)
    page.show()
    qtbot.wait(20)

    def field_label(control):
        return control.validation_field.findChild(QLabel, "fieldLabel")

    jira_label = field_label(page.jira)
    description_label = field_label(page.description)
    developer_label = field_label(page.developer)
    prefix_label = field_label(page.temp_prefix)
    assert all((jira_label, description_label, developer_label, prefix_label))

    def y(widget):
        return widget.mapTo(page, QPoint(0, 0)).y()

    assert abs(y(jira_label) - y(description_label)) <= 2
    assert abs(y(developer_label) - y(prefix_label)) <= 2
    assert 4 <= y(page.create_folder) - (y(page.jira) + page.jira.height()) <= 20
    assert 4 <= y(developer_label) - (y(page.create_folder) + page.create_folder.height()) <= 24


def test_multi_schema_checklist_stays_close_to_its_heading(qtbot):
    page = MultiSchemaPage()
    qtbot.addWidget(page)
    page.resize(1240, 720)
    page.show()
    qtbot.wait(20)

    from PySide6.QtWidgets import QLabel

    heading = page.schemas_section.findChild(QLabel, "sectionTitle")
    assert heading is not None
    assert heading.height() <= 32
    summary_y = page.schema_summary.mapTo(page.schemas_section, QPoint(0, 0)).y()
    assert summary_y <= heading.height() + 40
    checks_y = next(iter(page.schema_checks.values())).mapTo(page.schemas_section, QPoint(0, 0)).y()
    assert checks_y <= summary_y + 100


def _compare_page(qtbot, columns: int = 4) -> TableComparePage:
    page = TableComparePage()
    qtbot.addWidget(page)
    names = ("id", *(f"field_{i}" for i in range(1, columns)))
    left = tc.TableData(
        "sample", "a", names, (("1", *("old" for _ in names[1:])),), file_path="left.csv"
    )
    right = tc.TableData(
        "sample", "b", names, (("1", *("new" for _ in names[1:])),), file_path="right.csv"
    )
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    return page


def test_table_compare_loads_csv_and_workbench_sql_into_same_source_grid(
    qtbot, monkeypatch, tmp_path
):
    sql_path = tmp_path / "development.sql"
    sql_path.write_text(
        "/*\n-- Query: SELECT * FROM schema_a.sample\n*/\n"
        "INSERT INTO `` (`id`,`value`) VALUES (1,'from SQL');\n",
        encoding="utf-8",
    )
    csv_path = tmp_path / "production.csv"
    csv_path.write_text("id,value\n1,from CSV\n", encoding="utf-8")
    monkeypatch.setattr(
        "sqltools.ui.table_compare_page.QFileDialog.getOpenFileNames",
        lambda *_args: ([str(sql_path), str(csv_path)], ""),
    )
    settings_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        "sqltools.app.QSettings",
        lambda: QSettings(str(settings_path), QSettings.Format.IniFormat),
    )

    window = MainWindow(["TABLE_COMPARE"])
    qtbot.addWidget(window)
    window.resize(1240, 790)
    window.show()
    page = window.pages[0]
    page._add_files()
    qtbot.waitUntil(lambda: len(page.sources) == 2, timeout=5000)

    assert {table.export_format for _label, table, _info in page.sources} == {"csv", "sql"}
    assert [table.rows[0][0] for _label, table, _info in page.sources] == ["1", "1"]
    assert page.sources_view.model().rowCount() == 2
    assert page.sources_view.isVisible()
    assert page.compare_button.isEnabled()
    page._compare()
    qtbot.waitUntil(lambda: page.result is not None, timeout=5000)
    assert page.result.counts["changed"] == 1


@pytest.mark.parametrize("size", [(800, 600), (1240, 790)])
def test_table_compare_source_actions_stay_aligned_with_export_list(qtbot, size):
    window = MainWindow(["TABLE_COMPARE"])
    qtbot.addWidget(window)
    window.resize(*size)
    window.show()
    qtbot.wait(30)
    page = window.pages[0]
    toolbar = page.findChild(QWidget, "tableCompareSourceToolbar")

    assert toolbar is not None
    assert toolbar.height() <= 36
    toolbar_bottom = toolbar.mapTo(page.source_section, QPoint(0, 0)).y() + toolbar.height()
    list_top = page.sources_view.mapTo(page.source_section, QPoint(0, 0)).y()
    assert 4 <= list_top - toolbar_bottom <= 12
    assert page.sources_view.isVisible()


def test_table_compare_shows_setup_controls_before_results(qtbot):
    window = MainWindow(["TABLE_COMPARE"])
    qtbot.addWidget(window)
    page = window.pages[0]
    names = ("id", "field_1", "field_2", "field_3")
    left = tc.TableData("sample", "a", names, (("1", "old", "old", "old"),), file_path="left.csv")
    right = tc.TableData("sample", "b", names, (("1", "new", "new", "new"),), file_path="right.csv")
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    window.resize(1240, 790)
    window.show()
    qtbot.wait(40)

    assert page.setup_layout.indexOf(page.comparison_section) >= 0
    assert page.sources_view.isVisible()
    assert page.key_combo.isVisible()
    assert page.columns_more_button.isVisible()
    assert page.compare_button.isVisible()
    assert page.compare_button.isEnabled()
    assert page.clear_sources_button.isEnabled()
    assert page.results_empty_state.isVisible()
    assert page.results_empty_hint.text() == "Run Compare to inspect matching rows and differences."
    assert page.result_toolbar.isHidden()
    assert page.result_filters.isHidden()
    assert page.result_view.isHidden()

    page.set_busy(True)
    assert not page.compare_button.isEnabled()
    page.set_busy(False)
    assert page.compare_button.isEnabled()

    page._compare()
    qtbot.waitUntil(lambda: page.result is not None, timeout=5000)
    assert page.result_toolbar.isVisible()
    assert page.result_filters.isVisible()
    assert page.result_view.isVisible()
    assert page.results_empty_state.isHidden()


def test_table_compare_clear_inputs_removes_old_result_status(qtbot, monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        "sqltools.app.QSettings",
        lambda: QSettings(str(settings_path), QSettings.Format.IniFormat),
    )
    window = MainWindow(["TABLE_COMPARE"])
    qtbot.addWidget(window)
    page = window.pages[0]
    window.statusBar().showMessage("Complete")
    page.summary_label.setText("1 changed row")
    page.status.setText("Compared 2 source rows.")

    page._clear_sources()

    assert page.result is None
    assert page.result_model.rowCount() == 0
    assert page.summary_label.text() == "Add at least two exports to compare."
    assert page.status.text() == ""
    assert not page.clear_sources_button.isEnabled()
    assert not page.results_empty_state.isHidden()
    assert page.result_toolbar.isHidden()
    assert page.result_filters.isHidden()
    assert page.result_view.isHidden()
    assert window.statusBar().currentMessage() == ""


def test_table_compare_compact_empty_screen_keeps_guidance_visible(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    page.resize(880, 480)
    page.show()
    qtbot.wait(20)

    assert page.results_host.isHidden()
    assert page.compact_empty_hint.isVisible()
    assert not page.clear_sources_button.isEnabled()
    assert not page.compare_button.isEnabled()
    assert page.compact_empty_hint.text() == (
        "Add at least two exports to compare; results will appear here."
    )


def test_table_compare_disables_compare_when_sources_share_no_key(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    first = tc.TableData("first", "a", ("id",), (("1",),), file_path="left.csv")
    second = tc.TableData("second", "b", ("code",), (("1",),), file_path="right.csv")
    page.sources = [("LEFT", first, {}), ("RIGHT", second, {})]

    page._refresh_sources()

    assert page.key_combo.count() == 0
    assert not page.compare_button.isEnabled()


def test_table_compare_short_window_collapses_setup_without_detail_overlap(qtbot):
    page = _compare_page(qtbot)
    page.resize(880, 480)
    page.show()
    qtbot.wait(20)
    assert page.results_host.isHidden()
    assert page.compact_empty_hint.isVisible()
    assert page.compact_empty_hint.text() == (
        "Comparison results will appear here after you run Compare."
    )

    result = tc.compare_compact([(label, table) for label, table, _ in page.sources], "id")
    page.result = result
    page.result_model.set_result(result, False)
    page._sync_results_presentation()
    page.results_host.show()
    page._collapse_setup()
    assert page.compact_empty_hint.isHidden()
    page.result_view.selectRow(0)
    qtbot.wait(20)

    assert page.source_section.isHidden()
    assert page.results_title.isVisible()
    assert page.details_row.isHidden()
    assert page.detail_view.isHidden()
    assert page.details_button.isVisible()
    assert page.result_view.geometry().height() >= 80


def test_table_compare_short_results_show_complete_rows(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    page.resize(644, 402)
    left = tc.TableData("sample", "a", ("id", "value"), (("1", "old"), ("2", "old"), ("3", "old")))
    right = tc.TableData("sample", "b", ("id", "value"), (("1", "new"), ("4", "new"), ("5", "new")))
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    page.show()
    qtbot.wait(20)
    page.result = tc.compare_compact([(label, table) for label, table, _ in page.sources], "id")
    page.result_model.set_result(page.result, False)
    page.results_host.show()
    page._collapse_setup()
    qtbot.wait(20)

    third_row = page.result_view.visualRect(page.result_model.index(2, 0))
    assert third_row.isValid()
    assert third_row.bottom() <= page.result_view.viewport().rect().bottom()


def test_compare_column_dialog_handles_many_columns_and_locks_key(qtbot):
    page = _compare_page(qtbot, columns=100)
    assert len(page._common_columns) == 100
    assert page.key_combo.currentText() == "id"
    assert page._column_selected["id"] is True
    assert "100" in page.columns_more_button.text()

    actions = {"clear": False, "cancelled": False, "closed": False, "error": None}

    def cancel_dialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            items = dialog.findChild(QListWidget)
            clear = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "Clear selection"
            )
            clear.click()
            actions["clear"] = items.count() == 100
        except Exception as error:  # Always dismiss the modal before surfacing a test failure.
            actions["error"] = error
        finally:
            if isinstance(dialog, QDialog):
                dialog.reject()
                actions["cancelled"] = True

    original = dict(page._column_selected)
    QTimer.singleShot(0, cancel_dialog)
    page._open_columns_dialog()
    assert actions["cancelled"] and actions["clear"] and actions["error"] is None
    assert page._column_selected == original

    actions["cancelled"] = False

    def accept_clear():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            clear = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "Clear selection"
            )
            clear.click()
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        except Exception as error:
            actions["error"] = error
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.accept()
            actions["closed"] = isinstance(dialog, QDialog) and not dialog.isVisible()

    QTimer.singleShot(0, accept_clear)
    page._open_columns_dialog()
    assert actions["closed"] and actions["error"] is None
    assert page._column_selected["id"] is True
    assert sum(page._column_selected.values()) == 1


def test_source_label_can_be_renamed_in_table_and_rejects_duplicates(qtbot):
    page = _compare_page(qtbot)
    index = page.sources_model.index(0, 0)
    assert page.sources_model.setData(index, "DEVELOPMENT")
    assert page.sources[0][0] == "DEVELOPMENT"
    assert page.sources_model.data(page.sources_model.index(0, 0)) == "DEVELOPMENT"
    page.sources_model.setData(page.sources_model.index(1, 0), "DEVELOPMENT")
    assert page.sources[1][0] == "RIGHT"
