@echo off
REM padsynth setup: create a local venv and install declared dependencies.
REM Needs package-index access. An existing environment is reused, not deleted.
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required but `py` was not found.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed; fix network/packages and re-run.
  exit /b 1
)
echo Setup complete. Launch with 0Start.cmd (preferably in Windows Terminal).
