@echo off
setlocal
set SCRIPT_DIR=%~dp0
if defined PYTHON (
  set PYEXE=%PYTHON%
) else (
  set PYEXE=py
)
%PYEXE% "%SCRIPT_DIR%.agents\skills\codex-claude-unison\scripts\bootstrap_portable.py" --mode auto --target "%CD%" --replace-existing --yes %*
exit /b %ERRORLEVEL%
