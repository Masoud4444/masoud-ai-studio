@echo off
setlocal
set "APP_DIR=%~dp0.."
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required for this source/developer utility.
  exit /b 2
)
py -3 "%APP_DIR%\desktop\data_audit.py" %*
exit /b %errorlevel%
