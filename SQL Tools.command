#!/bin/bash
# SQL Tools developer launcher. Release builds are self-contained .app bundles.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    exec "$SCRIPT_DIR/.venv/bin/python" -m sqltools
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --directory "$SCRIPT_DIR" python -m sqltools
fi

osascript -e 'display dialog "Install uv to run the SQL Tools source checkout. For a self-contained release, use a signed SQL Tools release supplied by your organization." buttons {"OK"} default button "OK" with icon caution'
exit 1
