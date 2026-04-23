# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec file for SQL Tools GUI
# =============================================================================

import os
from pathlib import Path

block_cipher = None

ALL_FEATURES = [
    "INSERT_CONSOLIDATOR",
    "DB_AUTOMATION",
    "WORKFILE_GENERATOR",
    "MULTI_SCHEMA",
]

BASE_HIDDENIMPORTS = [
    # Ensure logic package root exists for dynamic imports
    "logic",
    # tkinter
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
]

FEATURE_TO_HIDDENIMPORTS = {
    "INSERT_CONSOLIDATOR": [
        "logic.insert_consolidator",
        # openpyxl sub-modules that PyInstaller can miss
        "openpyxl",
        "openpyxl.cell._writer",
        "openpyxl.styles.stylesheet",
        "openpyxl.styles.fills",
        "openpyxl.styles.fonts",
        "openpyxl.styles.borders",
        "openpyxl.styles.alignment",
        "openpyxl.styles.protection",
        "openpyxl.writer.excel",
        "openpyxl.reader.excel",
        "openpyxl.utils",
        "openpyxl.utils.dataframe",
    ],
    "DB_AUTOMATION": [
        "logic.db_automation",
    ],
    "WORKFILE_GENERATOR": [
        "logic.workfile_generator",
    ],
    "MULTI_SCHEMA": [
        "logic.multi_schema_combiner",
    ],
}


def _normalize_features(raw_features):
    normalized = []
    seen = set()
    for item in raw_features:
        token = str(item).strip().upper()
        if not token or token not in ALL_FEATURES or token in seen:
            continue
        normalized.append(token)
        seen.add(token)
    return normalized


def _load_selected_features():
    raw = os.environ.get("SQL_TOOLS_FEATURES", "")
    if raw:
        selected = _normalize_features(raw.split(","))
        if selected:
            return selected

    profile_path = Path("generated") / "build_profile.py"
    if profile_path.exists():
        namespace = {}
        exec(profile_path.read_text(encoding="utf-8"), namespace)
        selected = _normalize_features(namespace.get("ENABLED_FEATURES", []))
        if selected:
            return selected

    # Fallback to full build
    return list(ALL_FEATURES)


selected_features = _load_selected_features()

hiddenimports = list(BASE_HIDDENIMPORTS)
for feature in selected_features:
    hiddenimports.extend(FEATURE_TO_HIDDENIMPORTS.get(feature, []))

# Keep deterministic order while removing duplicates
hiddenimports = list(dict.fromkeys(hiddenimports))

datas = [
    # Include shared assets (icon, etc.)
    ("assets", "assets"),
]
if Path("generated").exists():
    datas.append(("generated", "generated"))

a = Analysis(
    ["sql_tools.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages we do not need
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "tensorflow",
        "torch",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SQL Tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets\\icon.ico",
    version_info=None,
)
