@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\activate.bat" (
  echo Run scripts\setup-windows.bat first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
alembic upgrade head
if errorlevel 1 (
  echo Database migration failed. Backend was not started.
  pause
  exit /b 1
)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
