@echo off
setlocal
cd /d "%~dp0.."
echo ==========================================
echo   Masoud AI Studio - Windows Setup
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer and enable Add to PATH.
  goto failed
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  python --version
  goto failed
)

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 20 or newer and enable Add to PATH.
  goto failed
)
node -e "const v=process.versions.node.split('.').map(Number); process.exit(v[0] >= 20 ? 0 : 1)"
if errorlevel 1 (
  echo Node.js 20 or newer is required.
  node --version
  goto failed
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto failed

python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed

cd frontend
call npm install
if errorlevel 1 goto failed
call npm run build
if errorlevel 1 goto failed
cd ..

if not exist "data" mkdir data
alembic upgrade head
if errorlevel 1 goto failed

echo.
echo Setup completed.
echo Start scripts\start-backend-windows.bat in one terminal.
echo Start scripts\start-frontend-windows.bat in a second terminal.
echo Then open http://127.0.0.1:5173
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above, fix the prerequisite or error, and retry.
pause
exit /b 1
