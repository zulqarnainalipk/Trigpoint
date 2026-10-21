@echo off
setlocal
cd /d "%~dp0"

rem Opens TrigPoint on the demo roster (synthetic scenes). To edit your own file:
rem   set SITE_CURATOR_SITES=C:\path\to\sites.json
rem Optional Earth Engine key: set EE_SERVICE_ACCOUNT_KEY_FILE=C:\path\to\key.json

if defined SITE_CURATOR_SITES echo Editing: %SITE_CURATOR_SITES%

set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"

start "" http://127.0.0.1:8765
"%PY%" server.py
pause
