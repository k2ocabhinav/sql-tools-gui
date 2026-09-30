from pathlib import Path

from openpyxl import load_workbook

from logic import table_comparator, workfile_generator
from sqltools.services import (
    FeatureOutcome,
    cancel_prepared_run,
    commit_file_run,
    prepare_file_run,
    run_db_automation,
    run_insert,
    run_multi_schema,
    run_workfile,
)


class _Context:
    job_id = "test-job"

    def check_cancelled(self):
        return None

    def report(self, _message, _value=-1):
        return None


def test_compact_compare_honors_selected_columns():
    source_a = table_comparator.parse_workbench_csv_compact(
        "id,name,ignored\n1,A,old\n"
    )
    source_b = table_comparator.parse_workbench_csv_compact(
        "id,name,ignored\n1,A,new\n"
    )

    result = table_comparator.compare_compact(
        [("A", source_a), ("B", source_b)], "id", included_columns={"id", "name"}
    )

    assert result.columns == ("id", "name")
    assert result.counts["identical"] == 1


def test_compact_compare_preserves_first_seen_source_key_order():
    source_a = table_comparator.parse_workbench_csv_compact("id,value\n2,A\n1,B\n")
    source_b = table_comparator.parse_workbench_csv_compact("id,value\n1,B\n3,C\n")

    result = table_comparator.compare_compact([("A", source_a), ("B", source_b)], "id")

    assert [row.key for row in result.rows] == ["2", "1", "3"]
    assert result.rows[1].source_rows == (1, 0)


def test_comparison_model_formats_requested_cell(qtbot):
    from sqltools.ui.table_compare_page import ComparisonTableModel

    source_a = table_comparator.parse_workbench_csv_compact("id,name\n1,A\n")
    source_b = table_comparator.parse_workbench_csv_compact("id,name\n1,B\n")
    result = table_comparator.compare_compact(
        [("DEV", source_a), ("TEST", source_b)], "id"
    )
    model = ComparisonTableModel()
    model.set_result(result, show_identical=True)

    assert model.data(model.index(0, 0)) == "Changed"
    assert model.data(model.index(0, 2)) == "A  →  B"


def test_compact_sql_parser_preserves_null_and_quoted_delimiters():
    content = (
        "-- MySQL dump\n"
        "-- Query: SELECT * FROM dev.sample\n"
        "INSERT INTO `` (`id`,`note`,`nullable`,`literal`)\n"
        "VALUES (1, 'comma, and ;', NULL, 'NULL');\n"
    )

    table = table_comparator.parse_sql_export_compact(content)

    assert table.table_name == "sample"
    assert table.rows == (("1", "comma, and ;", None, "NULL"),)
    assert table.warnings == ()


def test_compact_csv_parser_checks_cancellation_while_streaming():
    content = "id,value\n" + "".join(f"{row},value\n" for row in range(5_000))
    checkpoints = 0

    def cancel_after_second_checkpoint():
        nonlocal checkpoints
        checkpoints += 1
        if checkpoints == 2:
            raise RuntimeError("cancelled")

    try:
        table_comparator._parse_workbench_csv_stream(
            iter(content.splitlines(keepends=True)),
            "",
            check_cancelled=cancel_after_second_checkpoint,
        )
    except RuntimeError as error:
        assert str(error) == "cancelled"
    else:
        raise AssertionError("The parser did not check cancellation.")

    assert checkpoints == 2


def test_prepared_outputs_leave_existing_files_untouched_until_commit(tmp_path: Path):
    destination = tmp_path / "outputs"
    destination.mkdir()
    (destination / "existing.sql").write_text("old", encoding="utf-8")

    def generate(stage, _context):
        (stage / "existing.sql").write_text("replacement", encoding="utf-8")
        (stage / "new.sql").write_text("new", encoding="utf-8")
        return FeatureOutcome("Prepared two outputs.")

    prepared = prepare_file_run(_Context(), destination, generate)

    assert (destination / "existing.sql").read_text(encoding="utf-8") == "old"
    assert len(prepared.existing) == 1
    result = commit_file_run(_Context(), prepared)

    assert result.status == "success"
    assert {path.name for path in result.artifacts} == {"existing.sql", "new.sql"}
    assert (destination / "existing.sql").read_text(encoding="utf-8") == "replacement"


def test_prepared_run_refuses_stale_overwrite_and_cleans_staging(tmp_path: Path):
    destination = tmp_path / "outputs"
    destination.mkdir()
    target = destination / "existing.sql"
    target.write_text("before", encoding="utf-8")

    def generate(stage, _context):
        (stage / target.name).write_text("generated", encoding="utf-8")
        return FeatureOutcome("Prepared output.")

    prepared = prepare_file_run(_Context(), destination, generate)
    target.write_text("user edit", encoding="utf-8")
    result = commit_file_run(_Context(), prepared)

    assert result.status == "failed"
    assert "changed after confirmation" in result.diagnostics[0]
    assert target.read_text(encoding="utf-8") == "user edit"
    assert not prepared.staging_directory.exists()


def test_cancel_prepared_run_discards_staged_files(tmp_path: Path):
    destination = tmp_path / "outputs"

    def generate(stage, _context):
        (stage / "pending.sql").write_text("pending", encoding="utf-8")
        return FeatureOutcome("Prepared output.")

    prepared = prepare_file_run(_Context(), destination, generate)
    cancel_prepared_run(prepared)

    assert not (destination / "pending.sql").exists()
    assert not prepared.staging_directory.exists()


def test_workfile_service_continues_version_in_existing_jira_folder(tmp_path, monkeypatch):
    base = tmp_path / "workfiles"
    existing_folder = base / "OP - 1234 [Existing description]"
    existing_folder.mkdir(parents=True)
    existing_file = existing_folder / "V20260929_01 sample_sp.sql"
    existing_file.write_text("previous version", encoding="utf-8")
    monkeypatch.setattr(workfile_generator, "get_current_date_stamp", lambda: "V20260929")

    prepared = run_workfile(
        _Context(),
        {
            "copy": False,
            "paste": "CREATE PROCEDURE `sample_sp`() BEGIN SELECT 1; END",
            "jira": "1234",
            "base_folder": str(base),
            "developer": "Tester",
            "temp_prefix": "temp_test_",
            "description": "New description",
            "create_jira_folder": True,
        },
    )

    assert "Output folder: " + str(existing_folder) in prepared.outcome.summary
    target_names = {target.name for _staged, target in prepared.artifacts}
    assert "V20260929_02 sample_sp.sql" in target_names
    assert "V20260929_01 sample_sp.sql" not in target_names
    assert existing_file.read_text(encoding="utf-8") == "previous version"

    outcome = commit_file_run(_Context(), prepared)

    assert outcome.status == "success"
    assert existing_file.read_text(encoding="utf-8") == "previous version"
    assert (existing_folder / "V20260929_02 sample_sp.sql").is_file()


def test_existing_feature_services_generate_and_commit_outputs(tmp_path: Path):
    insert_output = tmp_path / "insert-output"
    insert = run_insert(
        _Context(),
        {
            "paste": (
                "/*\n-- Query: SELECT * FROM dev.sample\n*/\n"
                "INSERT INTO `` (`id`) VALUES (1);\n"
                "INSERT INTO `` (`id`) VALUES (2);"
            ),
            "files": [],
            "input_folder": "",
            "output_folder": str(insert_output),
            "date_prefix": "20260929",
            "generate_combined": True,
            "excel": False,
        },
    )
    assert {target.name for _staged, target in insert.artifacts} == {
        "20260929_01_sample.sql",
        "20260929 Combined.sql",
    }
    assert commit_file_run(_Context(), insert).status == "success"

    automation_output = tmp_path / "automation-output"
    automation = run_db_automation(
        _Context(),
        {
            "mode": "paste",
            "paste": "CREATE PROCEDURE `sample_sp`() BEGIN SELECT 1; END",
            "input_folder": "",
            "output_folder": str(automation_output),
            "sequence": 1,
            "developer": "Tester",
            "description": "Test procedure",
        },
    )
    assert len(automation.artifacts) == 1
    assert commit_file_run(_Context(), automation).status == "success"

    schema_output = tmp_path / "schema-output"
    combined = run_multi_schema(
        _Context(),
        {
            "copy": False,
            "mode": "paste",
            "paste": "USE old_schema;\nSELECT 1;",
            "files": [],
            "input_folder": "",
            "schemas": ["schema_a", "schema_b"],
            "output_folder": str(schema_output),
            "filename": "release.sql",
        },
    )
    assert len(combined.artifacts) == 1
    assert commit_file_run(_Context(), combined).status == "success"
    saved_schema_sql = (schema_output / "release.sql").read_text(encoding="utf-8")
    assert "USE schema_a;" in saved_schema_sql
    assert "USE schema_b;" in saved_schema_sql


def test_comparison_excel_export_keeps_untrusted_text_as_text(tmp_path: Path):
    source_a = table_comparator.parse_workbench_csv_compact(
        "id,=formula\n1,=2+2\n"
    )
    source_b = table_comparator.parse_workbench_csv_compact(
        "id,=formula\n1,=2+2\n"
    )
    source_a = table_comparator.TableData(
        None, "=1+1", source_a.columns, source_a.rows, file_path="dev.csv"
    )
    source_b = table_comparator.TableData(
        None, "=1+1", source_b.columns, source_b.rows, file_path="test.csv"
    )
    comparison = table_comparator.compare_compact(
        [("DEV", source_a), ("TEST", source_b)], "id"
    )
    output_path = tmp_path / "comparison.xlsx"

    table_comparator.export_compact_multi_to_excel(comparison, str(output_path))
    sheet = load_workbook(output_path, read_only=True, data_only=False).active

    assert sheet["D1"].value == "=formula"
    assert sheet["D1"].data_type == "s"
    assert sheet["B2"].value == "=1+1"
    assert sheet["B2"].data_type == "s"
    assert sheet["D2"].value == "=2+2"
    assert sheet["D2"].data_type == "s"
