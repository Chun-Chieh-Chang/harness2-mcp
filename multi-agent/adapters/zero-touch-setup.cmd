@echo off
rem Double-click launcher: harness2-loop zero-touch (Windows, no bash needed)
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found on PATH. Install Python 3.8+ (and check "Add to PATH"),
  echo or run from a terminal that has python, then retry.
  pause
  exit /b 1
)
echo Running harness2-loop zero-touch installer (cross-platform Python version)...
echo.
python "%~dp0zero-touch-setup.py" %*
echo.
pause
