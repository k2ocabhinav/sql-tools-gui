"""Behavioral regressions for the final desktop layout and interaction review."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QPushButton

from logic import table_comparator as tc
from sqltools.app import MainWindow
from sqltools.ui.db_automation_page import DbAutomationPage
from sqltools.ui.insert_page import InsertPage
from sqltools.ui.multi_schema_page import MultiSchemaPage
from sqltools.ui.table_compare_page import TableComparePage
from sqltools.ui.workfile_page import WorkfilePage

MODE_PAGES = (InsertPage, DbAutomationPage, MultiSchemaPage)


@pytest.mark.parametrize("page_type", MODE_PAGES)
def test_checked_source_choice_changes_visible_input_once(page_type, qtbot):
    """Accessibility clients may change checked state without emitting clicked."""
    page = page_type()
    qtbot.addWidget(page)
    page.show()
    changes = []
    page.mode.currentIndexChanged.connect(changes.append)
    page.editor.setPlainText("SELECT 1;")
    page.input_folder.setText("/synthetic/input")
    picker = getattr(page, "files_edit", getattr(page, "file_edit", None))
    if picker is not None:
        picker.add_paths(["C:/synthetic/first.sql", "C:/synthetic/second.sql"])
    count = page.mode.content.count()
    for _ in range(3):
        for index in range(count):
            previous = page.mode.currentIndex()
            before = len(changes)
            page.mode.switch._buttons.button(index).setChecked(True)
            assert page.mode.currentIndex() == index
            assert page.mode.content.currentIndex() == index
            assert len(changes) == before + (index != previous)
    assert page.editor.toPlainText() == "SELECT 1;"
    assert page.input_folder.text() == "/synthetic/input"
    if picker is not None:
        assert picker.paths() == ["C:/synthetic/first.sql", "C:/synthetic/second.sql"]

    page.mode.switch.setFocus()
    qtbot.keyClick(page.mode.switch, Qt.Key.Key_Right)
    assert page.mode.currentIndex() == 0
    qtbot.keyClick(page.mode.switch, Qt.Key.Key_Left)
    assert page.mode.currentIndex() == count - 1
    assert page.mode.switch._buttons.checkedId() == count - 1


@pytest.mark.parametrize("page_type", MODE_PAGES)
def test_changing_mode_dismisses_irrelevant_error_and_keeps_input(page_type, qtbot):
    page = page_type()
    qtbot.addWidget(page)
    page.show()
    page.editor.setPlainText("SELECT 1;")
    page.set_field_error(page.editor, "Synthetic validation error")
    page.mode.setCurrentIndex(1)
    assert not page.editor.property("invalid")
    assert page.status.text() == ""
    page.mode.setCurrentIndex(0)
    assert page.editor.toPlainText() == "SELECT 1;"


@pytest.mark.parametrize("page_type", (*MODE_PAGES, WorkfilePage))
def test_clear_removes_errors_on_already_empty_fields(page_type, qtbot):
    page = page_type()
    qtbot.addWidget(page)
    page.show()
    field = page.base_folder if isinstance(page, WorkfilePage) else page.output_folder
    assert not field.text()
    page.set_field_error(field, "Choose an output folder.")
    assert field.validation_field.error_label.isVisible()
    page._clear()
    assert not field.property("invalid")
    assert field.validation_field.error_label.isHidden()
    assert page.status.text() == ""


@pytest.mark.parametrize("size", [(1024, 700), (1240, 790)])
def test_full_window_mode_changes_keep_source_anchor_and_actions_visible(
    qtbot, monkeypatch, tmp_path, size
):
    monkeypatch.setattr(
        "sqltools.app.QSettings",
        lambda: QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(*size)
    window.show()
    qtbot.wait(20)
    for page_index, page in enumerate(window.pages):
        window.nav_buttons[page_index].click()
        qtbot.wait(10)
        if not hasattr(page, "mode"):
            continue
        source_origin = page.mode.mapTo(window, QPoint(0, 0))
        page.editor.setPlainText("SELECT 1;\n" * 40)
        page.input_folder.setText("C:/synthetic/" + "very-long-folder-name/" * 15)
        for index in [*range(page.mode.content.count()), 0]:
            page.mode.switch._buttons.button(index).click()
            qtbot.wait(10)
            assert page.mode.mapTo(window, QPoint(0, 0)) == source_origin
            active = page.mode.content.currentWidget()
            assert active.isVisible()
            assert page.input_scroll.horizontalScrollBar().maximum() == 0
            for button in page.actions_row.findChildren(QPushButton):
                assert button.isVisible()
                assert window.rect().contains(button.mapTo(window, button.rect().bottomRight()))
        assert page.editor.toPlainText() == "SELECT 1;\n" * 40


def test_compare_remove_stays_disabled_without_selection_after_job(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    remove = next(button for button in page.findChildren(QPushButton) if button.text() == "Remove")
    page.set_busy(True)
    page.set_busy(False)
    assert not remove.isEnabled()
    table = tc.TableData("sample", "synthetic.csv", ("id", "value"), (("1", "before"),))
    page.sources = [("LEFT", table, {})]
    page._refresh_sources()
    page.sources_view.selectRow(0)
    assert remove.isEnabled()
    page.sources_view.clearSelection()
    page.set_busy(True)
    page.set_busy(False)
    assert not remove.isEnabled()


def test_compare_selected_detail_reflows_when_window_height_changes(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    page.resize(1000, 900)
    left = tc.TableData("sample", "left.csv", ("id", "value"), (("1", "before"),))
    right = tc.TableData("sample", "right.csv", ("id", "value"), (("1", "after"),))
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    page.result = tc.compare_compact([(label, table) for label, table, _ in page.sources], "id")
    page.result_model.set_result(page.result, False)
    page._sync_results_presentation()
    page.show()
    page.result_view.selectRow(0)
    qtbot.wait(20)
    assert page.detail_view.isVisible()
    page.resize(1000, 720)
    qtbot.wait(20)
    assert page.detail_view.isHidden()
    assert page.details_button.isVisible()
    page.resize(1000, 900)
    qtbot.wait(20)
    assert page.detail_view.isVisible()


@pytest.mark.parametrize("page_type", (*MODE_PAGES, WorkfilePage))
def test_source_and_path_controls_have_distinguishable_accessible_names(page_type, qtbot):
    page = page_type()
    qtbot.addWidget(page)
    assert page.editor.accessibleName()
    output = page.base_folder if isinstance(page, WorkfilePage) else page.output_folder
    assert output.accessibleName()
    if hasattr(page, "mode"):
        assert page.mode.switch.accessibleName()
        assert page.input_folder.accessibleName()
        assert page.input_folder.accessibleName() != output.accessibleName()


def _loaded_compare_page(qtbot, height=900):
    page = TableComparePage()
    qtbot.addWidget(page)
    page.resize(1000, height)
    left = tc.TableData("sample", "left.csv", ("id", "value"), (("1", "before"), ("2", "same")))
    right = tc.TableData("sample", "right.csv", ("id", "value"), (("1", "after"), ("2", "same")))
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    page.show()
    page.result = tc.compare_compact([(label, table) for label, table, _ in page.sources], "id")
    page.result_model.set_result(page.result, False)
    page._sync_results_presentation()
    return page


def test_compare_invalidation_clears_stale_filters_and_row_detail(qtbot):
    page = _loaded_compare_page(qtbot)
    page.result_view.selectRow(0)
    qtbot.wait(20)
    assert page.detail_view.isVisible()
    page.search.setText("nothing matches this")
    page.status_filter.setCurrentIndex(2)
    page._invalidate_result()
    assert page.search.text() == ""
    assert page.status_filter.currentIndex() == 0
    assert page.detail_view.isHidden()
    assert page.details_row.isHidden()
    assert page.details_button.isHidden()
    assert page.detail_model.rowCount() == 0


def test_compare_detail_hidden_by_user_stays_reachable_and_returns_on_new_selection(qtbot):
    page = _loaded_compare_page(qtbot)
    page.result_view.selectRow(0)
    qtbot.wait(20)
    page.details_hide_button.click()
    assert page.detail_view.isHidden()
    assert page.details_button.isVisible()
    page.resize(1000, 700)
    page.resize(1000, 900)
    qtbot.wait(20)
    assert page.detail_view.isHidden()
    page.result_view.clearSelection()
    page.result_view.selectRow(0)
    assert page.detail_view.isVisible()


def test_compare_filter_that_removes_selected_row_clears_its_detail(qtbot):
    page = _loaded_compare_page(qtbot)
    page.result_view.selectRow(0)
    qtbot.wait(20)
    assert page.detail_view.isVisible()
    page.result_model.set_visible([])
    assert page.detail_view.isHidden()
    assert page.detail_model.rowCount() == 0


def test_compare_compact_hint_explains_incompatible_columns(qtbot):
    page = TableComparePage()
    qtbot.addWidget(page)
    page.resize(1000, 500)
    page.show()
    left = tc.TableData("t", "left.csv", ("id",), (("1",),))
    right = tc.TableData("t", "right.csv", ("other",), (("1",),))
    page.sources = [("LEFT", left, {}), ("RIGHT", right, {})]
    page._refresh_sources()
    assert page.compact_empty_hint.isVisible()
    assert "share no columns" in page.compact_empty_hint.text()
    assert not page.compare_button.isEnabled()


@pytest.mark.parametrize("page_type", (InsertPage, WorkfilePage))
def test_checkboxes_do_not_inset_neighbouring_fields(page_type, qtbot):
    page = page_type()
    qtbot.addWidget(page)
    page.resize(1100, 800)
    page.show()
    qtbot.wait(20)
    anchor = page.output_folder if page_type is InsertPage else page.base_folder
    reference = anchor.validation_field
    field = (page.date_prefix if page_type is InsertPage else page.developer).validation_field
    assert field.mapTo(page, QPoint(0, 0)).x() - reference.mapTo(page, QPoint(0, 0)).x() == 0


def test_long_status_wraps_instead_of_widening_the_page(qtbot):
    page = WorkfilePage()
    qtbot.addWidget(page)
    page.show()
    width = page.minimumSizeHint().width()
    page._set_status("Failed  " + "/synthetic/very-long-folder-name" * 12, "failed")
    assert page.minimumSizeHint().width() == width
    assert page.status.toolTip()


def test_checked_source_segment_reserves_its_semibold_width(qtbot):
    page = DbAutomationPage()
    qtbot.addWidget(page)
    page.show()
    for button in page.mode.switch._buttons.buttons():
        bold = button.font()
        bold.setWeight(bold.Weight.DemiBold)
        assert button.minimumWidth() >= QFontMetrics(bold).horizontalAdvance(button.text())
