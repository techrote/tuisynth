@echo off
REM padsynth start: use the local environment, installing it first when needed
REM so the documented launch path always lands in the real TUI.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating local environment...
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11+ is required but `py` was not found.
    exit /b 1
  )
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import prompt_toolkit" >nul 2>nul
if errorlevel 1 (
  echo Installing TUI dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed; fix network/packages and re-run.
    exit /b 1
  )
)
".venv\Scripts\python.exe" padsynth.py %*
