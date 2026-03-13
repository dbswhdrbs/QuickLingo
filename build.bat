@echo off
echo ============================================
echo   QuickLingo v2.0 - Build
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)

REM Build EXE
echo.
echo [2/3] Building EXE... (takes 1-2 min)
python -m PyInstaller --onefile --noconsole --name "QuickLingo" translator.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Done!
echo.
echo   EXE location: dist\QuickLingo.exe
echo.
echo   Run the EXE. A blue Q icon will appear in the system tray.
echo   Settings window opens automatically on first run.
echo.
pause
