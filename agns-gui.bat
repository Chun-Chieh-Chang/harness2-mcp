@echo off
rem ============================================================
rem  Agnes x Harness^2 GUI launcher (double-click)
rem
rem  Starts a local web console at http://127.0.0.1:8630 and
rem  opens it in your default browser. All config comes from
rem  .agns_bridge.env -- no terminal commands needed.
rem
rem  Stop: close the "Agnes GUI" console window (or press Ctrl+C).
rem ============================================================
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

rem make sure the GUI file is found (handle running from anywhere)
if exist "agns_bridge\agns_gui.py" (
    set "GUI=agns_bridge\agns_gui.py"
) else (
    echo [error] agnes_bridge\agns_gui.py not found next to this bat.
    pause
    exit /b 1
)

title Agnes GUI
echo Starting Agnes x Harness^2 console...
echo   open in browser : http://127.0.0.1:8630
echo   stop with Ctrl+C
echo.

rem auto-open the browser ~1.5s after the server binds
start "" /b cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8630"

python "%GUI%"
