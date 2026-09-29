# Native PyInstaller bundle for the Qt Widgets application.
import json
import sys
from pathlib import Path
import PyInstaller
from PyInstaller.utils.hooks.qt import pyside6_library_info

sys.path.insert(0, str(Path.cwd()))
from sqltools import __version__ as VERSION

ALL_FEATURES = [
    "INSERT_CONSOLIDATOR",
    "DB_AUTOMATION",
    "WORKFILE_GENERATOR",
    "MULTI_SCHEMA",
    "TABLE_COMPARE",
]
FEATURE_MODULES = {
    "INSERT_CONSOLIDATOR": ["sqltools.ui.insert_page", "logic.insert_consolidator"],
    "DB_AUTOMATION": ["sqltools.ui.db_automation_page", "logic.db_automation"],
    "WORKFILE_GENERATOR": ["sqltools.ui.workfile_page", "logic.workfile_generator"],
    "MULTI_SCHEMA": ["sqltools.ui.multi_schema_page", "logic.multi_schema_combiner"],
    "TABLE_COMPARE": [
        "sqltools.ui.table_compare_page",
        "logic.table_comparator",
        "logic.insert_consolidator",
        "logic.multi_schema_combiner",
    ],
}

try:
    profile = json.loads(Path("generated/build_profile.json").read_text(encoding="utf-8"))
    selected_features = profile.get("enabled_features", ALL_FEATURES)
except (OSError, ValueError):
    selected_features = ALL_FEATURES
selected_features = [feature for feature in ALL_FEATURES if feature in selected_features]
if not selected_features:
    selected_features = ALL_FEATURES

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
    "_pyi_rth_utils",
    "_pyi_rth_utils.qt",
    "sqltools.jobs",
    "sqltools.services",
    "sqltools.theme",
    "sqltools.smoke",
]
for feature in selected_features:
    hiddenimports.extend(FEATURE_MODULES[feature])
if any(feature in selected_features for feature in ("INSERT_CONSOLIDATOR", "TABLE_COMPARE")):
    hiddenimports.extend(["openpyxl", "openpyxl.cell._writer", "openpyxl.writer.excel"])
hiddenimports = list(dict.fromkeys(hiddenimports))

# Size trimming. Everything here is provably unused by SQL Tools: the code only
# uses QtCore/QtGui/QtWidgets, reads and writes UTF-8 files, and never opens a
# network connection. hashlib falls back to its built-in implementations without
# OpenSSL, and zipfile/shutil treat lzma and bz2 as optional.
EXCLUDED_MODULES = [
    # Heavy scientific/GUI stacks that a stray dependency could otherwise pull in.
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2", "torch",
    # Qt Python bindings the app never imports. (The QtDBus *library* stays: the
    # macOS platform plugin links it; only its Python binding is dropped.)
    "PySide6.QtNetwork", "PySide6.QtDBus",
    # Networking / TLS stack (~4 MB with OpenSSL).
    "ssl", "_ssl", "_hashlib",
    # Interpreter self-tests and interactive helpers.
    "_testcapi", "_testlimitedcapi", "_testinternalcapi", "_testmultiphase",
    "unittest", "pydoc", "doctest", "pdb", "readline",
    # Optional compression back-ends.
    "lzma", "_lzma", "bz2", "_bz2",
    # Legacy East-Asian codecs; every file this app reads or writes is UTF-8.
    "_codecs_jp", "_codecs_cn", "_codecs_hk", "_codecs_kr", "_codecs_tw",
    "_codecs_iso2022", "_multibytecodec",
]

datas = []
profile_path = Path("generated/build_profile.json")
if profile_path.exists():
    datas.append((str(profile_path), "generated"))

runtime_icon = Path("assets/icon.png")
if runtime_icon.exists():
    datas.append((str(runtime_icon), "assets"))

icon = Path("assets/icon.icns" if sys.platform == "darwin" else "assets/icon.ico")
icon_path = str(icon) if icon.exists() else None
platform_plugins = pyside6_library_info.collect_plugins("platforms")
if not platform_plugins:
    # PyInstaller's default collector uses glob patterns, which treat square
    # brackets in paths as character classes. Resolve the essential Qt platform
    # plugins with pathlib when the checkout lives in a path containing square brackets.
    plugin_dir = Path(pyside6_library_info.location["PluginsPath"]) / "platforms"
    platform_plugins = [
        (str(path), "PySide6/Qt/plugins/platforms")
        for path in plugin_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".dll", ".dylib", ".so"}
    ]

a = Analysis(
    ["sqltools/__main__.py"],
    pathex=[".", str(Path(PyInstaller.__file__).parent / "fake-modules")],
    binaries=platform_plugins,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[*EXCLUDED_MODULES],
    noarchive=False,
)

# Symbol stripping only shrinks Mach-O binaries; it is a no-op cost elsewhere.
STRIP_SYMBOLS = sys.platform == "darwin"

# PyInstaller's Qt hooks bundle every image-format plugin, the SVG icon engine, a
# touch plugin, the QtNetwork/QtSvg libraries and all Qt translations. The app only shows PNG artwork
# (built into QtGui), so drop them. Kept on purpose: the native platform and
# style plugins, offscreen (the build smoke test runs without a display) and
# QtDBus (the macOS platform plugin links it).
UNUSED_QT_PARTS = (
    "plugins/imageformats", "plugins/iconengines", "plugins/generic",
    "qminimal", "qtnetwork", "qt6network", "qtsvg", "qt6svg",
    # Qt's own UI strings in ~90 languages; the app never installs a QTranslator.
    "pyside6/qt/translations", "pyside6/translations",
)


def _is_unused(entry):
    name = str(entry[0]).replace("\\", "/").lower()
    return any(part in name for part in UNUSED_QT_PARTS)


a.binaries = [entry for entry in a.binaries if not _is_unused(entry)]
a.datas = [entry for entry in a.datas if not _is_unused(entry)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SQL Tools",
    debug=False,
    strip=STRIP_SYMBOLS,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
collected = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=STRIP_SYMBOLS,
    upx=False,
    name="SQL Tools",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collected,
        name="SQL Tools.app",
        icon=icon_path,
        bundle_identifier="org.sqltools.desktop",
        info_plist={
            "CFBundleName": "SQL Tools",
            "CFBundleDisplayName": "SQL Tools",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
