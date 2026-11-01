@echo off
REM YouTube Channel Studio: one-click launcher for Windows. Double-click this file.
REM First run installs everything (a few minutes). Later runs just start the app.
setlocal
cd /d "%~dp0"
title YouTube Channel Studio

REM 1. Find Python 3.11+ (the "py" launcher first, then "python").
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Python 3.11 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and TICK "Add python.exe to PATH" in the installer.
  echo Then double-click this file again.
  echo.
  pause
  exit /b 1
)

REM 2. Private Python environment + packages (only when missing or requirements changed).
if not exist ".venv\Scripts\python.exe" (
  echo Creating the private environment...
  %PY% -m venv .venv || goto :fail
)
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo Installing packages. This takes a few minutes the first time...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
  copy /y requirements.txt .venv\requirements.installed >nul
)

REM 3. Settings file (the app's Setup page fills it in for you).
if not exist ".env" if exist ".env.example" copy /y ".env.example" ".env" >nul

REM 4. ffmpeg builds the video. Offer to install it if missing.
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo ffmpeg is not installed yet. It is needed to build videos.
  choice /c YN /m "Install it now with winget"
  if not errorlevel 2 (
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    echo.
    echo ffmpeg installed. Close this window and double-click run_app.bat once more so it is found.
    pause
    exit /b 0
  )
  echo Skipping. The app's Setup page will remind you.
)

REM 5. Start the app; it opens in your browser at http://localhost:8501
echo.
echo Starting YouTube Channel Studio. Keep this window open while you use the app. Close it to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false
goto :eof

:fail
echo.
echo Something went wrong during setup (see the message above). Take a photo or copy the text and ask for help.
pause
exit /b 1
