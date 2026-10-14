@echo off
REM padsynth setup - creates a local venv and installs dependencies.
setlocal
cd /d "%~dp0"
if not exist .venv (
    echo [padsynth] creating virtual environment...
    py -3 -m venv .venv || goto :fail
)
echo [padsynth] installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fail
echo.
echo [padsynth] ready. Run 0Start.cmd  (or  .venv\Scripts\python.exe -m padsynth)
exit /b 0
:fail
echo [padsynth] setup failed. Install Python 3.11+ and rerun.
pause
exit /b 1