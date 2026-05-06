@echo off
setlocal
set SCRIPT_DIR=%~dp0
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py "%SCRIPT_DIR%bootstrap_portable.py" %*
  exit /b %ERRORLEVEL%
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%SCRIPT_DIR%bootstrap_portable.py" %*
  exit /b %ERRORLEVEL%
)
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%bootstrap.ps1" %*
exit /b %ERRORLEVEL%
