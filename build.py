from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALL_FEATURES = (
    "INSERT_CONSOLIDATOR",
    "DB_AUTOMATION",
    "WORKFILE_GENERATOR",
    "MULTI_SCHEMA",
    "TABLE_COMPARE",
)


def selected_features(raw: str) -> tuple[str, ...]:
    requested = {part.strip().upper() for part in raw.split(",") if part.strip()}
    if not requested or requested == {"ALL"}:
        return ALL_FEATURES
    invalid = requested.difference(ALL_FEATURES)
    if invalid:
        raise ValueError(f"Unknown feature(s): {', '.join(sorted(invalid))}")
    result = tuple(feature for feature in ALL_FEATURES if feature in requested)
    if not result:
        raise ValueError("At least one feature must be selected.")
    return result


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def create_portable_zip(app_dir: Path, portable: Path) -> None:
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path("SQL Tools") / path.relative_to(app_dir))


def windows_installer_command(
    compiler: str, version: str, app_dir: Path, output_dir: Path, script: Path
) -> list[str]:
    return [
        compiler,
        f"/DAppVersion={version}",
        f"/DAppSource={app_dir}",
        f"/O{output_dir}",
        str(script),
    ]


def build_profile_payload(version: str, features: tuple[str, ...], *, public: bool) -> dict:
    from logic.private_defaults import profile_schemas, profile_workfile_defaults

    return {
        "version": version,
        "enabled_features": features,
        "default_schemas": profile_schemas(public=public),
        **profile_workfile_defaults(public=public),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a native SQL Tools release artifact.")
    parser.add_argument(
        "--features",
        default="ALL",
        help="ALL or a comma-separated subset of the five feature IDs.",
    )
    parser.add_argument(
        "--no-installer",
        action="store_true",
        help="Skip optional Inno Setup compilation on Windows (still create portable output).",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Build with generic schema and workfile defaults instead of local private defaults.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "sql-tools-builds",
        help="Build workspace and artifact directory (default: a local folder under the OS temp directory).",
    )
    args = parser.parse_args()
    try:
        features = selected_features(args.features)
    except ValueError as error:
        parser.error(str(error))

    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows" and machine not in {"amd64", "x86_64"}:
        parser.error("Windows release builds currently target x64 only.")
    if system not in {"Windows", "Darwin"}:
        parser.error("Run release builds natively on Windows x64 or macOS.")
    if system == "Darwin" and machine not in {"arm64", "aarch64", "x86_64", "amd64"}:
        parser.error("macOS release builds target Apple Silicon (arm64) or Intel (x64).")
    architecture = "x64" if machine in {"amd64", "x86_64"} else "arm64"

    from sqltools import __version__ as version
    build_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    output_dir = args.output_root.expanduser().resolve() / build_id
    work_dir = output_dir / "work"
    dist_dir = output_dir / "dist"
    output_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    profile_path = ROOT / "generated" / "build_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(build_profile_payload(version, features, public=args.public), indent=2) + "\n",
        encoding="utf-8",
    )
    build_env = os.environ.copy()
    build_env["SQL_TOOLS_FEATURES"] = ",".join(features)
    build_env["SQL_TOOLS_VERSION"] = version
    build_env.setdefault("QT_QPA_PLATFORM", "offscreen")
    smoke_env = build_env.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_FONTDIR",
        "DYLD_FRAMEWORK_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
    ):
        smoke_env.pop(name, None)
    smoke_env["QT_QPA_PLATFORM"] = "offscreen"
    github_output = build_env.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as output:
            output.write(f"build_dir={output_dir}\n")

    print(f"Building SQL Tools {version} for {system} {machine}: {', '.join(features)}")
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "SQL Tools.spec",
            "--noconfirm",
            "--clean",
            "--workpath",
            str(work_dir),
            "--distpath",
            str(dist_dir),
        ],
        env=build_env,
    )

    if system == "Windows":
        app_dir = dist_dir / "SQL Tools"
        executable = app_dir / "SQL Tools.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"Expected application executable was not produced: {executable}")
        sign_windows((executable,), build_env)
        run([str(executable), "--smoke-test"], env=smoke_env)
        portable = output_dir / f"SQL Tools {version} Windows x64 portable.zip"
        create_portable_zip(app_dir, portable)
        print(f"Portable build: {portable}")

        if not args.no_installer:
            compiler = shutil.which("ISCC.exe") or shutil.which("ISCC")
            if compiler:
                script = ROOT / "packaging" / "windows" / "SQL Tools.iss"
                run(
                    windows_installer_command(compiler, version, app_dir, output_dir, script),
                    env=build_env,
                )
                installers = sorted(output_dir.glob("SQL Tools Setup *.exe"))
                if installers:
                    sign_windows((installers[-1],), build_env)
                    print(f"Installer: {installers[-1]}")
            else:
                print("Inno Setup (ISCC) is not installed; the portable ZIP is ready.")
    else:
        app_bundle = dist_dir / "SQL Tools.app"
        executable = app_bundle / "Contents" / "MacOS" / "SQL Tools"
        if not executable.is_file():
            raise FileNotFoundError(f"Expected application bundle was not produced: {app_bundle}")
        sign_macos(app_bundle, build_env)
        run([str(executable), "--smoke-test"], env=smoke_env)
        disk_image = output_dir / f"SQL Tools {version} macOS {architecture}.dmg"
        run(
            [
                "diskutil",
                "image",
                "create",
                "from",
                "--format",
                # LZMA: about a quarter smaller than zlib (UDZO); needs macOS 10.15+.
                "ULMO",
                str(app_bundle),
                str(disk_image),
            ],
            env=build_env,
        )
        notary_profile = build_env.get("SQL_TOOLS_NOTARY_PROFILE")
        if notary_profile:
            run(
                ["xcrun", "notarytool", "submit", str(disk_image), "--keychain-profile", notary_profile, "--wait"],
                env=build_env,
            )
            run(["xcrun", "stapler", "staple", str(disk_image)], env=build_env)
        print(f"Application bundle: {app_bundle}")
        print(f"Disk image: {disk_image}")

    # PyInstaller's intermediate files are 100+ MB and only useful for debugging a build.
    shutil.rmtree(work_dir, ignore_errors=True)
    print(f"Build output: {output_dir}")
    return 0


def sign_windows(files: tuple[Path, ...], env: dict[str, str]) -> None:
    thumbprint = env.get("SQL_TOOLS_SIGN_THUMBPRINT", "").strip()
    if not thumbprint:
        print("Windows outputs are unsigned; configure SQL_TOOLS_SIGN_THUMBPRINT for organization signing.")
        return
    signtool = env.get("SQL_TOOLS_SIGNTOOL") or shutil.which("signtool.exe") or shutil.which("signtool")
    if not signtool:
        raise RuntimeError("A signing thumbprint is set, but SignTool is not available.")
    for file in files:
        run(
            [
                signtool,
                "sign",
                "/sha1",
                thumbprint,
                "/fd",
                "SHA256",
                "/tr",
                "http://timestamp.digicert.com",
                "/td",
                "SHA256",
                str(file),
            ],
            env=env,
        )


def sign_macos(app_bundle: Path, env: dict[str, str]) -> None:
    identity = env.get("SQL_TOOLS_CODESIGN_IDENTITY", "").strip()
    if identity:
        run(
            [
                "codesign",
                "--force",
                "--deep",
                "--options",
                "runtime",
                "--timestamp",
                "--sign",
                identity,
                str(app_bundle),
            ],
            env=env,
        )
        run(["codesign", "--verify", "--deep", "--strict", str(app_bundle)], env=env)
    elif env.get("SQL_TOOLS_NOTARY_PROFILE"):
        raise RuntimeError("Notarization requires SQL_TOOLS_CODESIGN_IDENTITY.")
    else:
        print("macOS outputs are unsigned; configure a Developer ID identity for distribution.")


if __name__ == "__main__":
    raise SystemExit(main())
