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

if not exist ".env" (
  echo Creating a local encryption key in .env...
  python -c "import base64,secrets,pathlib; p=pathlib.Path('.env'); p.write_text('MASOUD_STUDIO_CREDENTIAL_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()+'\n',encoding='utf-8',newline='')"
  if errorlevel 1 goto failed
)

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
echo Setup completed. Double-click scripts\start-studio-windows.bat to launch the studio.
echo The local app will open at http://127.0.0.1:8000
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above, fix the prerequisite or error, and retry.
pause
exit /b 1
