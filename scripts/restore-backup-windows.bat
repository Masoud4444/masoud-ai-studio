@echo off
setlocal
if "%~1"=="" (
  echo Usage: restore-backup-windows.bat "C:\path\to\masoud-studio-backup.zip" [--verify]
  exit /b 2
)
set "APPDIR=%~dp0.."
set "PYTHONPATH=%APPDIR%"
python "%APPDIR%\desktop\restore_backup.py" "%~1" %~2
exit /b %ERRORLEVEL%
