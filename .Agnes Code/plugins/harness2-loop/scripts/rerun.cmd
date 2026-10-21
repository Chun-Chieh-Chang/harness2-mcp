@echo off
REM Windows fallback for harness2-loop hooks.
REM Use this only if your Agnes Code hook runner cannot execute `sh -c`
REM (no POSIX shell on PATH). Usage: rerun.cmd build-failure  |  rerun.cmd commit
python "%~dp0rerun_recipe.py" %1
