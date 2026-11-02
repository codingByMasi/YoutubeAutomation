@echo off
REM YouTube Channel Studio: one-click launcher for Windows. Double-click this file.
REM First run installs everything (a few minutes). Later runs just start the app.
setlocal
cd /d "%~dp0"
title YouTube Channel Studio

REM 1. Find a SUPPORTED Python: 3.12 preferred, then 3.11, then 3.13.
REM    Newer versions (3.14, 3.15...) often lack ready-made wheels for numpy, onnxruntime and others, so pip fails.
set "PY="
for %%V in (3.12 3.11 3.13) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo No supported Python was found on this PC. This app needs Python 3.11, 3.12 or 3.13 ^(3.12 is best^).
  echo Newer versions such as 3.14 or 3.15 do not work yet because some packages have no installer for them.
  echo 1. Download Python 3.12 from https://www.python.org/downloads/release/python-3128/
  echo 2. In the installer, TICK "Add python.exe to PATH" on the first screen.
  echo    You can keep your newer Python installed; this launcher picks 3.12 automatically.
  echo 3. Double-click run_app.bat again.
  echo If Windows opened the Microsoft Store instead, ignore it and use the python.org link above.
  echo.
  pause
  exit /b 1
)
echo Using Python: %PY%

REM 2. Private Python environment + packages (only when missing or requirements changed).
REM    An old .venv built with an unsupported Python is deleted and rebuilt.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo The existing private environment uses an unsupported Python. Rebuilding it...
    rmdir /s /q .venv
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the private environment...
  %PY% -m venv .venv || goto :fail
)
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo Installing packages. This takes a few minutes the first time. Please wait...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :pipfail
  copy /y requirements.txt .venv\requirements.installed >nul
  REM Word-accurate captions (faster-whisper) are optional: if this fails, captions are timed from the script instead.
  ".venv\Scripts\python.exe" -m pip install "faster-whisper>=1.0" >nul 2>&1 || echo Note: optional faster-whisper could not be installed. Captions will be timed from the script. That is fine.
)

REM 3. Settings file (the app's Setup page fills it in for you).
if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
  ) else (
    echo LLM_PROVIDER=claude_code> ".env"
  )
)

REM 4. Streamlit asks for an email on its very first run and waits forever. Answer it for the user.
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>&1
  > "%USERPROFILE%\.streamlit\credentials.toml" (
    echo [general]
    echo email = ""
  )
)
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

REM 5. ffmpeg builds the video. Offer to install it if missing.
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo ffmpeg is not installed yet. It is needed to build videos.
  where winget >nul 2>&1
  if errorlevel 1 (
    echo Windows' "winget" tool was not found, so it cannot be installed automatically.
    echo You can install it later from https://www.gyan.dev/ffmpeg/builds/ . The app still opens without it.
  ) else (
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
)

REM 6. Start the app; it opens in your browser at http://localhost:8501
echo.
echo Starting YouTube Channel Studio. Keep this window open while you use the app. Close it to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false
if errorlevel 1 goto :fail
goto :eof

:pipfail
echo.
echo Installing packages failed. Usual causes: no internet connection, or a VPN/firewall blocking pip.
echo Check your internet, then double-click run_app.bat again. It resumes where it stopped.
pause
exit /b 1

:fail
echo.
echo Something went wrong (see the message above). Take a photo or copy the text and ask for help.
pause
exit /b 1
