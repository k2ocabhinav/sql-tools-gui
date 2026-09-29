#!/bin/bash
# SQL Tools developer launcher. Release builds are self-contained .app bundles.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Keep the Python environment outside the project folder: cloud-synced folders
# (OneDrive) reject files such as ".lock" that Python packages contain.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/sql-tools}"

if [ -x "$UV_PROJECT_ENVIRONMENT/bin/python" ]; then
    cd "$SCRIPT_DIR" && exec "$UV_PROJECT_ENVIRONMENT/bin/python" -m sqltools
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --directory "$SCRIPT_DIR" python -m sqltools
fi

osascript -e 'display dialog "Install uv to run the SQL Tools source checkout. For a self-contained release, use a signed SQL Tools release supplied by your organization." buttons {"OK"} default button "OK" with icon caution'
exit 1
