@echo off
setlocal
cd /d "%~dp0.."
echo ==========================================
echo   Masoud AI Studio - Windows Setup
echo ==========================================
python --version
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer and enable Add to PATH.
  pause
  exit /b 1
)
node --version
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 20 or newer and enable Add to PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
cd frontend
call npm install
if errorlevel 1 goto failed
cd ..
call ".venv\Scripts\activate.bat"
alembic upgrade head
if errorlevel 1 goto failed
echo.
echo Setup completed. Start the backend and frontend using the two start scripts.
pause
exit /b 0
:failed
echo.
echo Setup failed. Read the error above, then retry.
pause
exit /b 1
