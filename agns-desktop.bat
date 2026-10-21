@echo off
rem ============================================================
rem  Agnes x Harness^2 one-click desktop runner (B3 + A1 + P1)
rem  Double-click from the harness2 repo root.
rem
rem  Steps:
rem    [1/5] load .agns_bridge.env
rem    [2/5] PICK EXECUTOR  1 = bundled deterministic worker
rem                        2 = real Agnes headless CLI (AGNES_CLI)
rem    [3/5] ensure harness2 installed
rem    [4/5] run the Agnes-substrate recursion demo
rem    [5/5] show result JSON + open runs\agns_demo in Explorer
rem ============================================================
setlocal enableextensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

rem ---- [1/5] load config ----
echo.
echo === [1/5] loading .agns_bridge.env ===
set "AGNES_CLI="
set "AGNES_API_URL="
if exist ".agns_bridge.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".agns_bridge.env") do (
        if /i "%%A"=="AGNES_CLI" set "AGNES_CLI=%%B"
        if /i "%%A"=="AGNES_API_URL" set "AGNES_API_URL=%%B"
    )
) else (
    echo [warn] .agns_bridge.env not found; using in-screen values.
)
if defined AGNES_CLI (echo        AGNES_CLI (from file) = %AGNES_CLI%) else (echo        AGNES_CLI (from file) = (empty))

rem ---- [2/5] pick executor ----
echo.
echo === [2/5] pick the rollout executor ===
echo    [1] bundled deterministic worker  (reproducible, no Agnes CLI / no API)
echo    [2] real Agnes headless CLI       (drives your Agnes Code via AGNES_CLI)
set "PICK=1"
set /p "PICK=  Pick 1 or 2 (default 1): "
if not defined PICK set "PICK=1"

if /i "%PICK%"=="2" goto :use_real

rem ---- worker path ----
set "AGNES_CLI="
echo        chosen: bundled deterministic worker
goto :run

:use_real
echo.
if defined AGNES_CLI (
    echo        chosen: real Agnes CLI = %AGNES_CLI%
    goto :run
)
echo    AGNES_CLI is empty. Paste your Agnes non-interactive command,
echo    e.g.  agnes run --headless
echo    (runs with cwd = staged workspace, env AGNES_TASK / AGNES_WORKSPACE;
echo     it writes answer.txt there OR prints the answer to stdout.)
set /p "AGNES_CLI=  AGNES_CLI: "
if not defined AGNES_CLI (
    echo [error] no AGNES_CLI given; aborting.
    pause
    exit /b 1
)
goto :run

rem ---- [3/5] ensure installed ----
:run
echo.
echo === [3/5] ensuring harness2 is installed ===
python -c "import harness2" 2>nul
if errorlevel 1 (
    echo        installing editable package...
    python -m pip install -e . || (
        echo [error] pip install failed. Create a venv, or install dependencies manually.
        pause
        exit /b 1
    )
) else (
    echo        harness2 already importable.
)

rem ---- [4/5] run demo ----
echo.
echo === [4/5] running Agnes-substrate recursion demo (k=2, both modes) ===
if defined AGNES_CLI (
    echo        executor = real Agnes CLI: %AGNES_CLI%
) else (
    echo        executor = bundled deterministic worker
)
python -m harness2.cli.agns_demo --output runs/agns_demo --k 2 --mode both || (
    echo [error] demo run failed; see output above.
    pause
    exit /b 1
)

rem ---- [5/5] result ----
echo.
echo === [5/5] result ===
type "runs\agns_demo\agns_demo.json"
echo.
start "" explorer "runs\agns_demo"

if defined AGNES_API_URL (
    echo Tip: Path A configured (AGNES_API_URL=%AGNES_API_URL%).
    echo       To run harness2 against Agnes as the model, double-click
    echo       agnes_bridge\agns-bridge-up.bat
) else (
    echo Tip: to enable Path A (Agnes as model endpoint), fill AGNES_API_URL in
    echo       .agns_bridge.env, then start the bridge:
    echo           python -m agnes_bridge.agnes_openai_proxy
)

echo.
pause
