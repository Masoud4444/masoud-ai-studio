@echo off
setlocal
cd /d "%~dp0.."
echo ==========================================
echo   Masoud AI Studio - Local Launch
echo ==========================================

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup-windows.bat first.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo The production frontend has not been built.
  echo Run scripts\setup-windows.bat to install dependencies and build it.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
  echo Database migration failed. Studio was not started.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',8000)); s.close(); raise SystemExit(1 if r == 0 else 0)"
if errorlevel 1 (
  echo Port 8000 is already in use. Close the existing service before launching another copy.
  pause
  exit /b 1
)

start "Masoud AI Studio Backend" cmd /k "cd /d ""%CD%"" && "".venv\Scripts\python.exe"" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"

echo Waiting for the local studio service...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='http://127.0.0.1:8000/health'; for($i=0;$i -lt 30;$i++){ try { $r=Invoke-RestMethod -Uri $url -TimeoutSec 2; if($r.status -eq 'ok' -and $r.service -eq 'masoud-ai-studio'){ Start-Process 'http://127.0.0.1:8000'; exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
  echo The backend did not become healthy within 30 seconds.
  echo Check the Masoud AI Studio Backend window for the startup error.
  pause
  exit /b 1
)
echo Studio opened in your default browser.
echo Keep the backend window open while using the studio.
exit /b 0
