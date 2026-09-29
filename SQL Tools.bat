@echo off
setlocal
cd /d "%~dp0"
rem Keep the Python environment outside synced folders such as OneDrive.
if not defined UV_PROJECT_ENVIRONMENT set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\SQLTools\venv"
where uv >nul 2>nul
if errorlevel 1 (
    echo Install uv to run SQL Tools from source. See README.md.
    pause
    exit /b 1
)
uv run python -m sqltools
if errorlevel 1 pause
