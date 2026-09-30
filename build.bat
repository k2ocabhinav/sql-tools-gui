@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo Install uv and Python 3.13 before building SQL Tools.
    echo See README.md for setup instructions.
    exit /b 1
)

uv sync --extra dev
if errorlevel 1 exit /b %errorlevel%

uv run python build.py %*
exit /b %errorlevel%
