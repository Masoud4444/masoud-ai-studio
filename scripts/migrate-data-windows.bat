@echo off
setlocal
set "APP_DIR=%~dp0.."
if exist "%APP_DIR%\MasoudStudioMigrate.exe" (
  "%APP_DIR%\MasoudStudioMigrate.exe" %*
  exit /b %errorlevel%
)
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required for this source/developer utility.
  exit /b 2
)
py -3 "%APP_DIR%\desktop\migrate_data.py" %*
exit /b %errorlevel%
