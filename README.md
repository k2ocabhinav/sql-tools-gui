# SQL Tools

SQL Tools is a desktop workspace for preparing database release files and comparing exported tables. It runs on Python 3.13 with PySide6/Qt Widgets and keeps SQL transformations in the independently testable `logic` modules.

The five tools are INSERT Consolidator, DB Automation Converter, Workfile Generator, Multi-Schema Combiner, and Table Compare. The app uses a compact navigation rail, shared progress and diagnostics, searchable comparison results, and one background operation at a time. File-producing operations prepare outputs in a staging directory, show collisions together, and replace files only after confirmation. Cancelling or failing preparation leaves existing output files unchanged.

To disable the brief navigation and Activity-panel transitions, choose **View → Reduce motion**. This preference is saved locally.

## Run from source

Clone the repository. Install [uv](https://docs.astral.sh/uv/) and use it to install Python 3.13 and the locked project dependencies.

On macOS:

```sh
brew install uv
uv python install 3.13
uv sync --locked
uv run --locked python -m sqltools
```

On Windows, open PowerShell and install uv with WinGet. Reopen PowerShell after installation so it can find `uv`:

```powershell
winget install --id=astral-sh.uv -e
uv python install 3.13
uv sync --locked
uv run --locked python -m sqltools
```

### Cloud-synced folders (OneDrive, iCloud, Dropbox)

Do not let the Python environment live inside a synced folder: OneDrive rejects file names that Python packages contain (for example `.lock`) and reports sync errors. `SQL Tools.command`, `SQL Tools.bat` and `build.bat` already keep it outside the project by setting `UV_PROJECT_ENVIRONMENT`. For your own terminal commands, set it once (macOS/Linux shown; on Windows use `setx UV_PROJECT_ENVIRONMENT "%LOCALAPPDATA%\SQLTools\venv"`):

```sh
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/sql-tools"
```

After syncing, you can also double-click `SQL Tools.command` on macOS or `SQL Tools.bat` on Windows. `python sql_tools.py` remains a compatibility entry point. Release artifacts are self-contained and do not require a separately installed Python runtime.

## Install a release

Build the artifact on its target OS and CPU architecture, then install it as follows:

- **Windows x64:** run `SQL Tools Setup <version> Windows x64.exe` for the per-user installer. For the portable build, extract `SQL Tools <version> Windows x64 portable.zip` to a writable folder and launch `SQL Tools\SQL Tools.exe`.
- **macOS:** open `SQL Tools <version> macOS <architecture>.dmg`, then drag `SQL Tools.app` to Applications in Finder. The app bundle targets the machine's native architecture.

For managed company devices, use an organization-approved signed and notarized release. Ask IT to approve the publisher or package when endpoint policy blocks an unsigned build; do not bypass device controls.

## Build release artifacts

Install the development dependencies and build on Windows x64, Apple Silicon, or Intel macOS:

```sh
uv sync --locked --extra dev
uv run --locked --extra dev python build.py
```

The macOS app is about 57 MB and the `.dmg` about 15 MB (LZMA-compressed): the spec drops Qt parts and Python modules this app never uses (network/TLS, image-format plugins, translations, legacy codecs), and the build's smoke test runs each feature's real workflow so trimming cannot silently break one. PyInstaller's intermediate `work` folder is deleted after a successful build.

Windows builds a portable ZIP and, when Inno Setup is installed, an optional installer. macOS builds a self-contained `.app` and compressed `.dmg`. Build workspaces and artifacts go in a unique folder under the OS temporary directory by default, outside cloud-synced checkouts; pass `--output-root PATH` to choose another local directory. The packaged executable runs in smoke-test mode with development Python and Qt search paths removed. PyInstaller must run on the target platform; this project does not cross-compile.

To build a feature subset, pass comma-separated feature IDs:

```sh
uv run --locked python build.py --features DB_AUTOMATION,TABLE_COMPARE
```

Windows signing uses `SQL_TOOLS_SIGN_THUMBPRINT` and an available Windows SDK `signtool`. macOS signing uses `SQL_TOOLS_CODESIGN_IDENTITY`; set `SQL_TOOLS_NOTARY_PROFILE` to submit and staple the DMG through Apple's notary service. Keep signing credentials in the developer or CI secret store, outside the repository.

For local builds, copy `.sqltools-private.example.json` to the ignored `.sqltools-private.json` and edit the schema, developer-name, and temporary-prefix defaults for your environment. The ordinary build embeds those local defaults in its generated profile. For a package intended to share or publish, use `uv run --locked python build.py --public`; this forces generic schema and workfile defaults even when a private settings file exists. Unsigned builds can trigger SmartScreen, Gatekeeper, or managed-device application controls. Signing establishes publisher identity, but it does not override a policy that blocks unapproved software.

## Development and validation

```sh
uv sync --locked --extra dev
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev python -m sqltools --smoke-test
```

The smoke test constructs every enabled Qt page, parses a small export, and runs a comparison without opening a window. The GitHub Actions workflow runs tests and native build smoke checks on Windows x64, Apple Silicon macOS, and Intel macOS.

## Architecture and boundaries

- `sqltools/app.py` owns startup, navigation, settings, logging, and output approval.
- `sqltools/ui/` contains feature pages and reusable widgets.
- `sqltools/jobs.py` runs one worker at a time. Workers do not access Qt widgets or models. Table parsing, comparison, export, and output commits check cancellation while running; legacy converters stop at the next operation boundary.
- `sqltools/services.py` adapts page requests to existing feature logic and stages generated files.
- `logic/` owns SQL and comparison behavior. The compact table path stores rows as tuples and comparison results as source-row offsets to avoid duplicate dictionaries for large exports.
- `tests/` covers established transformations, selected-column comparison, staged-output safety, and text-safe Excel export.

The app reads files supplied by the user. Live RDS connections, stored credentials, and CSV/JSON comparison exports are not implemented in this release. Before direct database features ship, they need secure credential handling, TLS, timeouts, read-only query boundaries, and bounded fetches.

## Design references

- [Qt Widgets](https://doc.qt.io/qt-6/qtwidgets-index.html), [Qt high-DPI guidance](https://doc.qt.io/qt-6/highdpi.html), and [Qt font database](https://doc.qt.io/qt-6/qfontdatabase.html)
- [WCAG text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)

Detailed product-design, architecture, and publication notes are maintained separately and intentionally excluded from the public source.
