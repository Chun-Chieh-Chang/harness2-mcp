@echo off
rem ============================================================
rem  Agnes x Harness^2  Evolutionary dev console -- one-click GUI
rem
rem  Double-click to open a browser chat console:
rem    - you type dev tasks like in Agnes Code
rem    - the agent works in evolve\demo_project with real tools
rem      (list / read / write / run shell)
rem    - after EVERY task, the Harness^2 evolution engine revises
rem      .harness/ (systemprompt, tool guidance, guardrails, memory)
rem      so the next task starts stronger
rem
rem  Model config: .agns_bridge.env at the repo root (no install).
rem  Stop: close this window or press Ctrl+C.
rem ============================================================
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

title Agnes Evolution Console
echo Starting Agnes x Harness^2 evolution console...
echo   UI at : http://127.0.0.1:8640
echo   stop with Ctrl+C
echo.

python evolve\evolve_gui.py

endlocal
