import json

from logic.private_defaults import (
    PUBLIC_DEVELOPER_NAME,
    PUBLIC_SCHEMA_DEFAULTS,
    PUBLIC_TEMP_PREFIX,
    default_developer_name,
    default_schemas,
    default_temp_prefix,
    profile_schemas,
    profile_workfile_defaults,
    schema_code,
)


def test_private_defaults_fall_back_to_generic_list(tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(tmp_path / "missing.json"))

    assert default_schemas() == PUBLIC_SCHEMA_DEFAULTS


def test_private_defaults_validate_identifiers_and_duplicates(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(path))

    path.write_text(json.dumps({"default_schemas": ["sample_a", "sample_b"]}), encoding="utf-8")
    assert default_schemas() == ["sample_a", "sample_b"]
    assert schema_code("sample_a") == "sample_a"

    path.write_text(json.dumps({"default_schemas": ["sample_a", "bad schema"]}), encoding="utf-8")
    assert default_schemas() == PUBLIC_SCHEMA_DEFAULTS

    path.write_text(json.dumps({"default_schemas": ["sample_a", "sample_a"]}), encoding="utf-8")
    assert default_schemas() == PUBLIC_SCHEMA_DEFAULTS


def test_public_build_profile_ignores_local_schema_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"default_schemas": ["site_schema_a"]}), encoding="utf-8")
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(path))

    assert profile_schemas(public=False) == ["site_schema_a"]
    assert profile_schemas(public=True) == PUBLIC_SCHEMA_DEFAULTS


def test_workfile_defaults_are_configurable_and_validated(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(path))

    assert default_developer_name() == PUBLIC_DEVELOPER_NAME
    assert default_temp_prefix() == PUBLIC_TEMP_PREFIX

    path.write_text(
        json.dumps({"developer_name": "Local Developer", "temp_prefix": "temp_local_"}),
        encoding="utf-8",
    )
    assert default_developer_name() == "Local Developer"
    assert default_temp_prefix() == "temp_local_"

    path.write_text(
        json.dumps({"developer_name": "Bad\nName", "temp_prefix": "bad prefix;"}),
        encoding="utf-8",
    )
    assert default_developer_name() == PUBLIC_DEVELOPER_NAME
    assert default_temp_prefix() == PUBLIC_TEMP_PREFIX


def test_public_workfile_profile_ignores_local_values(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"developer_name": "Local Developer", "temp_prefix": "temp_local_"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SQL_TOOLS_PRIVATE_CONFIG", str(path))

    assert profile_workfile_defaults(public=False) == {
        "developer_name": "Local Developer",
        "temp_prefix": "temp_local_",
    }
    assert profile_workfile_defaults(public=True) == {
        "developer_name": PUBLIC_DEVELOPER_NAME,
        "temp_prefix": PUBLIC_TEMP_PREFIX,
    }
