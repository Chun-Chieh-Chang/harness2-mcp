#!/usr/bin/env sh
# Thin wrapper for the harness2-loop zero-touch installer.
# The SSOT is now zero-touch-setup.py (cross-platform, stdlib-only).
# Prefer Python when available (avoids the Windows "no bash on PATH" problem);
# fall back to the legacy pure-sh logic only when no real python exists.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)

# find a usable python (guard against the Windows MS-Store `python` alias)
PYBIN=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys, os, shutil, subprocess, pathlib" >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done

if [ -n "$PYBIN" ]; then
  exec "$PYBIN" "$HERE/zero-touch-setup.py" "$@"
fi

echo "WARNING: no usable python found; using the legacy pure-sh zero-touch installer."
echo "         (recommend installing Python 3.8+ for the cross-platform version.)"
# Legacy path: reuse the old inlined logic by exec-ing a copy kept alongside.
# (If zero-touch-setup.sh.orig is missing, just point the user to python.)
if [ -f "$HERE/zero-touch-setup.sh.orig" ]; then
  exec sh "$HERE/zero-touch-setup.sh.orig" "$@"
else
  echo "ERROR: install Python 3.8+ and run:  python \"$HERE/zero-touch-setup.py\""
  exit 1
fi
