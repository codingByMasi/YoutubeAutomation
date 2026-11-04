# YouTube Channel Studio: one-command setup for Windows.
#   Right-click > Run with PowerShell, or in a terminal:  powershell -ExecutionPolicy Bypass -File setup.ps1
# It picks a supported Python (3.12, 3.11, 3.13), builds the private .venv, installs the packages, creates .env,
# downloads the caption model and ends with the preflight check. Safe to run again at any time.
param([switch]$SkipFix, [switch]$Offline)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; exit 1 }

# 1. A supported Python.
$py = $null
foreach ($v in "3.12", "3.11", "3.13") {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break }
}
if (-not $py) {
    $ok = & python -c "import sys; print(int((3,11) <= sys.version_info[:2] <= (3,13)))" 2>$null
    if ($ok -eq "1") { $py = @("python") }
}
if (-not $py) {
    Fail ("No supported Python found. Install Python 3.12 from https://www.python.org/downloads/release/python-3128/ " +
          "(tick 'Add python.exe to PATH'), then run this script again.")
}
Write-Host "Using Python: $($py -join ' ')"

# 2. Private environment (rebuilt if it was made with an unsupported Python).
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $good = & $venvPy -c "import sys; print(int((3,11) <= sys.version_info[:2] <= (3,13)))" 2>$null
    if ($good -ne "1") { Write-Host "Rebuilding the private environment (unsupported Python)..."; Remove-Item -Recurse -Force .venv }
}
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating the private environment..."
    & $py[0] $py[1..($py.Count)] -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create .venv. Close programs using the folder and try again." }
}

# 3. Packages.
Write-Host "Installing packages (a few minutes the first time)..."
& $venvPy -m pip install --disable-pip-version-check --upgrade pip | Out-Null
& $venvPy -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Package install failed. Check your internet / VPN, then run setup.ps1 again; it resumes." }
& $venvPy -m pip install --disable-pip-version-check "faster-whisper>=1.0"
if ($LASTEXITCODE -ne 0) { Write-Host "faster-whisper could not be installed; captions will be timed from estimates." -ForegroundColor Yellow }
Copy-Item requirements.txt .venv\requirements.installed -Force

# 4. Settings file.
if (-not (Test-Path .env)) {
    if (Test-Path .env.example) { Copy-Item .env.example .env } else { "LLM_PROVIDER=claude_code" | Set-Content .env -Encoding utf8 }
}

# 5. Preflight: checks everything and fixes what it can (ffmpeg via winget, caption model, missing packages).
$args2 = @("-m", "studio.cli", "preflight")
if (-not $SkipFix) { $args2 += "--fix" }
if ($Offline) { $args2 += "--offline" }
& $venvPy @args2
if ($LASTEXITCODE -ne 0) { Fail "Some checks still fail (lines marked [FAIL] above). Fix them, then run setup.ps1 again." }
Write-Host "`nAll set. Start the app with run_app.bat (or: .venv\Scripts\python -m streamlit run app.py)." -ForegroundColor Green
