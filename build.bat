@echo off
setlocal
cd /d "%~dp0"
rem Keep the Python environment outside synced folders such as OneDrive.
if not defined UV_PROJECT_ENVIRONMENT set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\SQLTools\venv"

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
