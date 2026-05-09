@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if defined PYTHON (
  set "PYEXE=%PYTHON%"
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYEXE=py"
  ) else (
    where python3 >nul 2>nul
    if not errorlevel 1 (
      set "PYEXE=python3"
    ) else (
      where python >nul 2>nul
      if not errorlevel 1 (
        set "PYEXE=python"
      ) else (
        echo Python 3.9+ is required. Set PYTHON or install py/python3/python. 1>&2
        exit /b 1
      )
    )
  )
)
"%PYEXE%" "%SCRIPT_DIR%.agents\skills\codex-claude-unison\scripts\bootstrap_portable.py" --mode auto --target "%CD%" --replace-existing --yes %*
exit /b %ERRORLEVEL%
