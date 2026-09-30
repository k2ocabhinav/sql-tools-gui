"""Small adapters between feature pages and the existing pure logic modules."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqltools.jobs import JobContext


@dataclass(slots=True)
class FeatureOutcome:
    summary: str
    diagnostics: list[str] = field(default_factory=list)
    clipboard_text: str | None = None
    artifacts: list[Path] = field(default_factory=list)
    payload: Any = None
    status: str = "success"


@dataclass(slots=True)
class PreparedRun:
    run_id: str
    staging_directory: Path
    destination_directory: Path
    artifacts: list[tuple[Path, Path]]
    existing: list[tuple[Path, tuple[int, int]]]
    outcome: FeatureOutcome


def prepare_file_run(
    context: JobContext,
    destination: str | Path,
    operation: Callable[[Path, JobContext], FeatureOutcome],
) -> PreparedRun:
    """Write into an isolated staging folder, leaving named outputs untouched."""
    context.check_cancelled()
    destination_path = Path(destination).expanduser().resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".sql-tools-stage-", dir=destination_path))
    try:
        outcome = operation(staging, context)
        context.check_cancelled()
        artifacts = sorted(
            ((path, destination_path / path.relative_to(staging))
             for path in staging.rglob("*") if path.is_file()),
            key=lambda pair: pair[1].as_posix().casefold(),
        )
        destinations = [target for _, target in artifacts]
        if len({os.path.normcase(str(path)) for path in destinations}) != len(destinations):
            raise ValueError("Two generated files would have the same output path.")
        existing = []
        for _, target in artifacts:
            if target.exists():
                info = target.stat()
                existing.append((target, (info.st_size, info.st_mtime_ns)))
        return PreparedRun(
            run_id=context.job_id,
            staging_directory=staging,
            destination_directory=destination_path,
            artifacts=artifacts,
            existing=existing,
            outcome=outcome,
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def commit_file_run(context: JobContext, prepared: PreparedRun) -> FeatureOutcome:
    """Atomically replace each file and report a partial commit if a later file fails."""
    existing_by_target = dict(prepared.existing)
    committed: list[Path] = []
    try:
        # Recheck every destination immediately before the first replace so an
        # external change never causes a partially approved run to overwrite data.
        for _, target in prepared.artifacts:
            recorded = existing_by_target.get(target)
            if recorded is None:
                if target.exists():
                    raise RuntimeError(f"Output appeared after preparation: {target.name}.")
                continue
            if not target.exists():
                raise RuntimeError(f"Output changed after confirmation: {target.name} was removed.")
            info = target.stat()
            if (info.st_size, info.st_mtime_ns) != recorded:
                raise RuntimeError(f"Output changed after confirmation: {target.name} was modified.")

        for staged, target in prepared.artifacts:
            context.check_cancelled()
            target.parent.mkdir(parents=True, exist_ok=True)
            # The staging folder is inside the destination, so os.replace is same-volume.
            os.replace(staged, target)
            committed.append(target)
            context.report(f"Saved {target.name}")
    except Exception as error:
        prepared.outcome.status = "partial" if committed else "failed"
        prepared.outcome.artifacts = committed
        prepared.outcome.diagnostics.append(str(error))
        return prepared.outcome
    finally:
        shutil.rmtree(prepared.staging_directory, ignore_errors=True)
    prepared.outcome.artifacts = committed
    return prepared.outcome


def cancel_prepared_run(prepared: PreparedRun) -> None:
    shutil.rmtree(prepared.staging_directory, ignore_errors=True)


def read_sql_file(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def run_insert(context: JobContext, request: dict) -> FeatureOutcome:
    from logic import insert_consolidator as logic

    date_prefix = request["date_prefix"] or datetime.now().strftime("%Y%m%d")
    generate_combined = request["generate_combined"]

    def operation(staging: Path, job: JobContext) -> FeatureOutcome:
        if request["paste"].strip():
            job.report("Consolidating pasted SQL")
            result = logic.process_pasted_to_files(
                request["paste"], str(staging), date_prefix, generate_combined
            )
        elif request["files"]:
            result = logic.process_files(
                request["files"], str(staging), date_prefix, generate_combined
            )
        else:
            source = Path(request["input_folder"])
            if not source.is_dir():
                raise ValueError("Choose an existing input folder or provide SQL/files.")
            result = logic.process_folder(
                str(source), str(staging), date_prefix, generate_combined
            )
        diagnostics = list(result.get("errors", []))
        if request["excel"] and result.get("processed"):
            logic.generate_excel_summary(result["processed"], str(staging), date_prefix)
        summary = [f"Files processed: {len(result.get('processed', []))}"]
        summary.extend(
            f"{item.get('output', item.get('input', 'output'))}  ·  "
            f"{item.get('records', 0)} rows"
            for item in result.get("processed", [])
        )
        if result.get("combined_file"):
            summary.append(f"Combined: {result['combined_file']}")
        status = "partial" if diagnostics and result.get("processed") else (
            "failed" if diagnostics else "success"
        )
        return FeatureOutcome("\n".join(summary), diagnostics, payload=result, status=status)

    return prepare_file_run(context, request["output_folder"], operation)


def run_db_automation(context: JobContext, request: dict) -> PreparedRun:
    from logic import db_automation as logic

    def operation(staging: Path, job: JobContext) -> FeatureOutcome:
        job.report("Converting database objects")
        if request["mode"] == "paste":
            result = logic.process_pasted_to_files(
                request["paste"], str(staging), request["sequence"],
                request["developer"], request["description"],
            )
        else:
            result = logic.process_folder(
                request["input_folder"], str(staging), request["sequence"],
                request["developer"], request["description"],
            )
        diagnostics = list(result.get("errors", []))
        lines = [f"Files created: {len(result.get('processed', []))}"]
        lines.extend(
            f"[{item.get('type', 'SQL')}] {item.get('output', 'output')}"
            for item in result.get("processed", [])
        )
        status = "partial" if diagnostics and result.get("processed") else (
            "failed" if diagnostics else "success"
        )
        return FeatureOutcome("\n".join(lines), diagnostics, payload=result, status=status)

    return prepare_file_run(context, request["output_folder"], operation)


def run_workfile(context: JobContext, request: dict) -> PreparedRun | FeatureOutcome:
    from logic import workfile_generator as logic

    if request["copy"]:
        context.report("Generating SQL for clipboard")
        result = logic.process_pasted_content_to_clipboard(
            request["paste"], request["jira"], request["developer"],
            request["temp_prefix"], request["description"],
        )
        errors = list(result.get("errors", []))
        return FeatureOutcome(
            f"Generated {len(result.get('processed', []))} object(s) for clipboard.",
            errors,
            clipboard_text=result.get("content") or None,
            payload=result,
            status="partial" if errors and result.get("content") else (
                "failed" if errors else "success"
            ),
        )

    def operation(staging: Path, job: JobContext) -> FeatureOutcome:
        base_folder = Path(request["base_folder"]).expanduser().resolve()
        jira_id = request["jira"].strip()
        if request["create_jira_folder"] and jira_id:
            existing_folder = logic.find_jira_folder(jira_id, str(base_folder))
            relative_folder = (
                Path(existing_folder).relative_to(base_folder) if existing_folder else None
            )
        else:
            relative_folder = Path()

        # The legacy generator checks existing filenames to choose its next version.
        # Seed only those names into staging so it sees the real sequence without
        # copying old output files into the commit set.
        seed_folder = staging / relative_folder if relative_folder is not None else staging
        if relative_folder is not None:
            seed_folder.mkdir(parents=True, exist_ok=True)
        seeded_files = []
        actual_folder = base_folder / relative_folder if relative_folder is not None else base_folder
        if actual_folder.is_dir():
            for existing_file in actual_folder.glob("*.sql"):
                marker = seed_folder / existing_file.name
                marker.touch(exist_ok=True)
                seeded_files.append(marker)

        job.report("Generating versioned workfiles")
        result = logic.process_pasted_content(
            request["paste"], jira_id, str(staging), request["developer"],
            request["temp_prefix"], request["description"],
            create_jira_folder_flag=request["create_jira_folder"],
        )
        for marker in seeded_files:
            marker.unlink(missing_ok=True)
        if result.get("folder_path"):
            result["folder_path"] = str(
                base_folder / Path(result["folder_path"]).relative_to(staging)
            )
        errors = list(result.get("errors", []))
        lines = [f"Output folder: {result.get('folder_path', staging)}"]
        lines.extend(
            f"[{item.get('type', 'SQL')}] {item.get('main_file', 'output')}"
            for item in result.get("processed", [])
        )
        return FeatureOutcome(
            "\n".join(lines), errors, payload=result,
            status="partial" if errors and result.get("processed") else (
                "failed" if errors else "success"
            ),
        )

    return prepare_file_run(context, request["base_folder"], operation)


def run_multi_schema(context: JobContext, request: dict) -> PreparedRun | FeatureOutcome:
    from logic import multi_schema_combiner as logic

    if request["copy"]:
        context.report("Combining schemas")
        if request["mode"] == "paste":
            result = logic.combine_text_for_schemas_to_clipboard(
                request["paste"], request["schemas"]
            )
        else:
            files = request["files"] or logic.get_sql_files_from_folder(request["input_folder"])
            result = logic.combine_for_schemas_to_clipboard(files, request["schemas"])
        errors = list(result.get("errors", []))
        return FeatureOutcome(
            f"Files combined: {result.get('files_processed', 0)}\n"
            f"Schemas: {', '.join(result.get('schemas', []))}",
            errors, clipboard_text=result.get("content") or None, payload=result,
            status="partial" if errors and result.get("content") else (
                "failed" if errors else "success"
            ),
        )

    def operation(staging: Path, job: JobContext) -> FeatureOutcome:
        job.report("Combining schemas")
        name = Path(request["filename"]).name
        if not name.lower().endswith(".sql"):
            name += ".sql"
        output_path = staging / name
        if request["mode"] == "paste":
            result = logic.combine_text_for_schemas(
                request["paste"], request["schemas"], str(output_path)
            )
        else:
            files = request["files"] or logic.get_sql_files_from_folder(request["input_folder"])
            result = logic.combine_for_schemas(files, request["schemas"], str(output_path))
        errors = list(result.get("errors", []))
        return FeatureOutcome(
            f"Files combined: {result.get('files_processed', 0)}\n"
            f"Schemas: {', '.join(result.get('schemas', []))}",
            errors, payload=result,
            status="partial" if errors and result.get("output_file") else (
                "failed" if errors else "success"
            ),
        )

    return prepare_file_run(context, request["output_folder"], operation)
