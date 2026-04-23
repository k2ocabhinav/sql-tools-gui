import tempfile
import unittest
from pathlib import Path

from logic import db_automation, multi_schema_combiner, workfile_generator


class RegressionTests(unittest.TestCase):
    def _convert_function(self, call_line: str) -> str:
        sql = (
            "CREATE FUNCTION `sample_fn` ()\n"
            "RETURNS INT\n"
            "BEGIN\n"
            f"{call_line}\n"
            "    RETURN 1;\n"
            "END;\n"
        )
        result = db_automation.process_single_object(
            sql,
            sequence_num=1,
            date_str="V20260423",
            timestamp_str="23 Apr 2026",
            developer_name="Tester",
        )
        self.assertIsNotNone(result)
        return result[0]

    def test_db_automation_comments_debug_v0_to_v9_and_base(self):
        for proc_name in ["sys_log_debug_sp", "sys_log_debug_v0_sp", "sys_log_debug_v9_sp"]:
            converted = self._convert_function(f"    CALL {proc_name}('x');")
            self.assertIn(f"-- CALL {proc_name}('x');", converted)

    def test_db_automation_does_not_comment_debug_v10(self):
        converted = self._convert_function("    CALL sys_log_debug_v10_sp('x');")
        self.assertIn("CALL sys_log_debug_v10_sp('x');", converted)
        self.assertNotIn("-- CALL sys_log_debug_v10_sp('x');", converted)

    def test_multi_schema_replaces_indented_use_line(self):
        content = "    USE db_old;\nSELECT 1;\n"
        converted = multi_schema_combiner.replace_use_statement(content, "db_new")
        self.assertNotIn("db_old", converted)
        self.assertEqual(converted.upper().count("USE "), 1)
        self.assertTrue(converted.startswith("USE db_new;"))

    def test_workfile_generator_parses_algorithm_and_sql_security_view(self):
        view_sql = (
            "CREATE ALGORITHM=UNDEFINED DEFINER=`ot_admin`@`%` SQL SECURITY DEFINER "
            "VIEW `all_pax_first_task_vw` AS SELECT 1;"
        )
        sql_type, object_name = workfile_generator.detect_sql_type(view_sql)
        self.assertEqual(sql_type, "VIEW")
        self.assertEqual(object_name, "all_pax_first_task_vw")

        combined = view_sql + "\n\n" + view_sql.replace("`all_pax_first_task_vw`", "`app_window_vw`")
        parts = workfile_generator.split_sql_objects(combined)
        self.assertEqual(len(parts), 2)

        result = workfile_generator.process_pasted_content_to_clipboard(combined, "1234")
        self.assertEqual(len(result["processed"]), 2)
        self.assertEqual(result["errors"], [])

    def test_db_automation_invalid_input_folder_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as output_dir:
            missing = str(Path(output_dir) / "missing-folder")
            result = db_automation.process_folder(missing, output_dir)
            self.assertEqual(result["processed"], [])
            self.assertTrue(result["errors"])
            self.assertIn("Input folder not found", result["errors"][0])

    def test_db_automation_folder_processing_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            input_dir.mkdir()

            (input_dir / "b.sql").write_text(
                "CREATE FUNCTION `b_fn` ()\nRETURNS INT\nBEGIN\n    RETURN 1;\nEND;\n",
                encoding="utf-8",
            )
            (input_dir / "a.sql").write_text(
                "CREATE FUNCTION `a_fn` ()\nRETURNS INT\nBEGIN\n    RETURN 2;\nEND;\n",
                encoding="utf-8",
            )

            result = db_automation.process_folder(str(input_dir), str(output_dir))
            self.assertEqual(result["errors"], [])
            sources = [item["source"] for item in result["processed"]]
            self.assertEqual(sources, ["a.sql", "b.sql"])
            sequences = [item["sequence"] for item in result["processed"]]
            self.assertEqual(sequences, [1, 2])


if __name__ == "__main__":
    unittest.main()
