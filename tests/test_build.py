from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("sql_tools_release_build", _ROOT / "build.py")
assert _SPEC is not None and _SPEC.loader is not None
_BUILD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BUILD)


def test_feature_selection_is_case_insensitive_and_stable():
    assert _BUILD.selected_features("table_compare, db_automation") == (
        "DB_AUTOMATION",
        "TABLE_COMPARE",
    )
    assert _BUILD.selected_features("all") == _BUILD.ALL_FEATURES


def test_feature_selection_rejects_unknown_features():
    with pytest.raises(ValueError, match="Unknown feature"):
        _BUILD.selected_features("NOT_A_FEATURE")


def test_public_build_profile_drops_local_schema_and_workfile_defaults(tmp_path, monkeypatch):
    config = tmp_path / "private.json"
    config.write_text(
        '{"default_schemas":["private_schema"],"developer_name":"Private Name",'
        '"temp_prefix":"private_"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(config))

    profile = _BUILD.build_profile_payload("2.0.0", ("TABLE_COMPARE",), public=True)

    assert profile == {
        "version": "2.0.0",
        "enabled_features": ("TABLE_COMPARE",),
        "default_schemas": [f"schema_{letter}" for letter in "abcdefg"],
        "developer_name": "Developer",
        "temp_prefix": "temp_",
    }


def test_packaged_gui_smoke_tolerates_consoleless_standard_streams(tmp_path):
    config = tmp_path / "public-settings.json"
    config.write_text(
        json.dumps({
            "default_schemas": [f"schema_{letter}" for letter in "abcdefg"],
            "developer_name": "Developer",
            "temp_prefix": "temp_",
        }),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SQL_TOOLS_PRIVATE_CONFIG"] = str(config)
    script = (
        "import sys; sys.stdout = None; sys.stderr = None; "
        "sys.argv = ['SQL Tools', '--smoke-test']; "
        "from sqltools.app import main; raise SystemExit(main())"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_windows_installer_command_keeps_paths_with_spaces_as_single_arguments(tmp_path):
    app_dir = tmp_path / "build output" / "SQL Tools"
    output_dir = tmp_path / "release files"
    script = tmp_path / "packaging" / "SQL Tools.iss"

    command = _BUILD.windows_installer_command(
        "C:/Inno Setup/ISCC.exe", "2.0.0", app_dir, output_dir, script
    )

    assert command == [
        "C:/Inno Setup/ISCC.exe",
        "/DAppVersion=2.0.0",
        f"/DAppSource={app_dir}",
        f"/O{output_dir}",
        str(script),
    ]


def test_portable_zip_preserves_runtime_tree_and_has_stable_order(tmp_path: Path):
    app_dir = tmp_path / "SQL Tools"
    (app_dir / "_internal" / "PySide6").mkdir(parents=True)
    (app_dir / "SQL Tools.exe").write_bytes(b"executable")
    (app_dir / "_internal" / "PySide6" / "QtCore.dll").write_bytes(b"runtime")
    portable = tmp_path / "SQL Tools portable.zip"

    _BUILD.create_portable_zip(app_dir, portable)

    with zipfile.ZipFile(portable) as archive:
        assert archive.namelist() == [
            "SQL Tools/SQL Tools.exe",
            "SQL Tools/_internal/PySide6/QtCore.dll",
        ]
        assert archive.read("SQL Tools/SQL Tools.exe") == b"executable"
        assert archive.read("SQL Tools/_internal/PySide6/QtCore.dll") == b"runtime"


def test_smoke_workflows_run_every_feature_against_real_services():
    from sqltools.smoke import CHECKS, run_feature_workflows

    assert set(CHECKS) == set(_BUILD.ALL_FEATURES)
    assert run_feature_workflows(list(CHECKS)) is None


def test_spec_trims_only_unused_parts_and_keeps_what_the_app_needs():
    spec = (_ROOT / "SQL Tools.spec").read_text(encoding="utf-8")
    # Trimmed: unused Qt bindings, TLS, translations, image-format plugins.
    for trimmed in ("PySide6.QtNetwork", '"ssl"', "plugins/imageformats", "qt/translations"):
        assert trimmed in spec
    # Must stay bundled: the macOS platform plugin links QtDBus, and the runtime
    # window/sidebar icon is loaded from assets/icon.png.
    assert '"PySide6.QtDBus"' in spec  # only its Python binding is excluded
    assert "libqcocoa" not in spec.split("UNUSED_QT_PARTS")[1].split(")")[0]
    assert "assets/icon.png" in spec
