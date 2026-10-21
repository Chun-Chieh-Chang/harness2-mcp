@echo off
rem ============================================================
rem  Agnes x Harness^2 - Path A one-click bridge launcher
rem
rem  What it does:
rem    1. cd to the harness2 repo root (next to this bat)
rem    2. start the local OpenAI-compatible bridge in THIS window
rem       (http://127.0.0.1:8620/v1 -> your Agnes endpoint)
rem    3. open a SECOND window that runs agnes_bridge_check.py,
rem       which polls the bridge until it answers 200, then
rem       prints the exact env-var block to run harness2.
rem
rem  .agns_bridge.env (one level up) is auto-loaded by the bridge.
rem ============================================================
setlocal enableextensions

rem Find repo root = parent of the folder containing this bat.
set "BRIDGE_DIR=%~dp0"
rem This bat lives inside the repo; bridge dir is agnes_bridge\ (repo root\agns_bridge\)
set "ROOT=%BRIDGE_DIR%.."
pushd "%ROOT%" 2>nul
if errorlevel 1 (
    echo [error] cannot resolve the harness2 repo root from %BRIDGE_DIR%
    echo         Place this bat in <repo>\agns_bridge\ and try again.
    popd
    pause
    exit /b 1
)
cd /d "%ROOT%"

echo.
echo === Agnes bridge launcher ===
echo   repo root : %ROOT%
echo   config    : .agns_bridge.env
echo   bridge    : http://127.0.0.1:%AGNES_PROXY_PORT:8620%/v1  (reads AGNES_PROXY_PORT from .agns_bridge.env if set)
echo.
echo Starting bridge in THIS window (Ctrl+C to stop).
echo Opening a second window to verify the link...
echo.

rem Second window: poll the bridge, show diagnostics + harness2 wiring.
start "Agnes bridge check" cmd /k "cd /d "%ROOT%" & python agnes_bridge\agns_bridge_check.py 90 & echo & echo --- press a key to close --- & pause"

rem First window: the bridge itself (blocks; Ctrl+C to stop).
python -m agnes_bridge.agnes_openai_proxy
popd
endlocal
