@echo off
REM padsynth launcher - use from Windows Terminal.
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [padsynth] missing .venv. Run Setup.cmd first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m padsynth %*