@echo off
setlocal EnableExtensions

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

set "WEB_HOST=%AEGIS_WEB_HOST%"
if "%WEB_HOST%"=="" set "WEB_HOST=127.0.0.1"
set "WEB_PORT=%AEGIS_WEB_PORT%"
if "%WEB_PORT%"=="" set "WEB_PORT=8000"
set "RENDER_PORT=%AEGIS_RENDER_PORT%"
if "%RENDER_PORT%"=="" set "RENDER_PORT=5001"
set "WEB_URL=http://%WEB_HOST%:%WEB_PORT%"

if "%MANIM_API_KEY%"=="" set "MANIM_API_KEY=dev-key-change-in-production"
set "RENDER_BACKEND_URL=http://127.0.0.1:%RENDER_PORT%"
if "%AEGIS_CLOUD_GENERATE_URL%"=="" set "AEGIS_CLOUD_GENERATE_URL=https://manim-main.vercel.app/api/generate"
set "PYTHONUNBUFFERED=1"

echo Aegis local launcher for Windows
echo Project: %ROOT_DIR%
echo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=python"
  ) else (
    echo Python 3 was not found. Install Python 3, then run this launcher again.
    pause
    exit /b 1
  )
)

where ffmpeg >nul 2>nul
if not %ERRORLEVEL%==0 (
  echo ffmpeg was not found. Install ffmpeg first, then run this launcher again.
  echo Recommended Windows install: winget install Gyan.FFmpeg
  pause
  exit /b 1
)

set "VENV_DIR=%AEGIS_LOCAL_VENV%"
if "%VENV_DIR%"=="" set "VENV_DIR=%ROOT_DIR%\.aegis-local-venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo Creating local Python environment...
  %PYTHON_CMD% -m venv "%VENV_DIR%"
  if not %ERRORLEVEL%==0 (
    echo Failed to create the Python environment.
    pause
    exit /b 1
  )
)

echo Installing/updating local render dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if not %ERRORLEVEL%==0 goto dependency_failed
"%VENV_PY%" -m pip install -r render_backend\requirements.txt
if not %ERRORLEVEL%==0 goto dependency_failed

echo.
echo Starting local render backend on http://127.0.0.1:%RENDER_PORT% ...
start "Aegis Render Backend" /D "%ROOT_DIR%\render_backend" cmd /k "set PORT=%RENDER_PORT%&& "%VENV_PY%" app.py"

echo Starting local Aegis Web on %WEB_URL% ...
start "Aegis Web" /D "%ROOT_DIR%" cmd /k ""%VENV_PY%" core\web_app.py --host %WEB_HOST% --port %WEB_PORT%"

echo Waiting for local services...
for /l %%i in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%RENDER_PORT%/health'; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%WEB_URL%/api/health'; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto ready
  )
  timeout /t 1 /nobreak >nul
)

echo Local services did not become healthy. Check the two Aegis command windows.
pause
exit /b 1

:ready
echo.
echo Ready: %WEB_URL%
echo Generation uses the configured cloud trial endpoint; rendering uses this computer.
start "" "%WEB_URL%"
pause
exit /b 0

:dependency_failed
echo Failed to install Python dependencies.
pause
exit /b 1
