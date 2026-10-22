# -*- coding: utf-8 -*-
"""Build the portable, zero-dependency harness2-loop integration bundle.

The integration layer is pure standard library (no third-party imports), so
the bundle below is fully self-contained and runnable on any machine that has
Python 3.12+ and the harness2 package installed.

Output:
  .agnes/artifacts/harness2-loop-portable.zip   (the portable artifact)
  .agnes/artifacts/harness2-loop-portable/manifest.json (what's inside)

Re-run any time to regenerate (idempotent; same inputs -> same zip contents).
"""
import os, json, shutil, zipfile, hashlib, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, ".agnes", "artifacts")
PKG = os.path.join(OUT_DIR, "harness2-loop-portable")
ZIP = os.path.join(OUT_DIR, "harness2-loop-portable.zip")

# What belongs in the portable bundle (path -> relative name inside the zip).
# Excludes runtime state (.state/), caches, and machine-local .env.
INCLUDE = [
    # MCP server (zero-dep stdio JSON-RPC)
    "mcp_server/harness2_mcp.py",
    "mcp_server/__init__.py",
    # Recipe
    "recipes/harness2-any-project.yaml",
    # Custom agent + skill
    ".agents/agents/harness2-dev-agent.md",
    ".agents/skills/harness2-develop/SKILL.md",
    # hooks plugin (source only, NO .state runtime, NO __pycache__)
    ".Agnes Code/plugins/harness2-loop/plugin.json",
    ".Agnes Code/plugins/harness2-loop/config.json",
    ".Agnes Code/plugins/harness2-loop/README.md",
    ".Agnes Code/plugins/harness2-loop/hooks/hooks.json",
    ".Agnes Code/plugins/harness2-loop/scripts/rerun_recipe.py",
    ".Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py",
    ".Agnes Code/plugins/harness2-loop/scripts/rerun.cmd",
    # multi-agent adapters
    "multi-agent/README.md",
    "multi-agent/adapters/git/post-commit.sh",
    "multi-agent/adapters/git/install.sh",
    "multi-agent/adapters/build-failure/record-build-failure.sh",
    "multi-agent/adapters/mcp/opencode.mcp.json",
    "multi-agent/adapters/mcp/antigravity.mcp.json",
    "multi-agent/adapters/mcp/workbuddy.mcp.json",
    "multi-agent/adapters/mcp/qoder.mcp.json",
    "multi-agent/adapters/mcp/trae.mcp.json",
    "multi-agent/adapters/mcp/cline.mcp.json",
    "multi-agent/adapters/mcp/kiro.mcp.json",
    "multi-agent/adapters/mcp/minimax.mcp.json",
    "multi-agent/adapters/opencode/quickstart.sh",
    # flowchart visual + audit pipeline + dev docs
    "scripts/verify-flowchart-spec.js",
    "dev_log.md",
    "handoff.md",
    "USER_GUIDE.md",
]

# zero-dependency proof: the Python files must import only stdlib modules.
def _stdlib_set():
    try:
        return set(__import__("sys").stdlib_names)
    except AttributeError:
        # Explicit stdlib allowlist (what the integration layer actually imports).
        return {
            "os", "sys", "json", "re", "subprocess", "shutil", "hashlib",
            "zipfile", "importlib", "sysconfig", "datetime", "time", "argparse",
            "pathlib", "urllib", "http", "socket", "ssl", "threading", "queue",
            "collections", "functools", "itertools", "contextlib", "typing",
            "dataclasses", "enum", "abc", "io", "tempfile", "base64", "copy",
            "math", "random", "string", "textwrap", "unicodedata", "weakref",
            "signal", "struct", "glob", "fnmatch", "warnings", "weakref",
        }

STDLIB = _stdlib_set() | {"__future__"}
PY_IMPORTS = re.compile(r"^\s*import\s+([A-Za-z_]\w*)|^\s*from\s+([A-Za-z_]\w*)\s+import", re.M)

def check_pure(target_path):
    code = open(target_path, encoding="utf-8").read()
    for m in PY_IMPORTS.finditer(code):
        mod = m.group(1) or m.group(2)
        if not mod:
            continue
        if mod in STDLIB:
            continue
        # bundled local modules (imported by other files in the same bundle)
        if mod == "rerun_recipe":
            continue
        print("  NON-DEP VIOLATION: %s imports third-party %r" % (target_path, mod))
        return False
    return True

def main():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG, exist_ok=True)

    manifest = {"bundle": "harness2-loop-portable", "files": [], "zero_dep": True}
    for rel in INCLUDE:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            print("  MISSING source: %s" % rel); manifest["zero_dep"] = False; continue
        # keep the ".Agnes Code"/".agents" folder shape inside the bundle
        dst = os.path.join(PKG, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        entry = {"path": rel, "bytes": os.path.getsize(dst),
                 "sha256": hashlib.sha256(open(dst, "rb").read()).hexdigest()[:16]}
        manifest["files"].append(entry)
        # pure-stdlib check for .py
        if rel.endswith(".py") and not check_pure(dst):
            manifest["zero_dep"] = False

    with open(os.path.join(PKG, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    # build the zip (flat, relative to PKG)
    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(PKG):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, os.path.dirname(PKG))
                z.write(full, arc)

    print("WROTE: %s  (%d files, %d bytes)" %
          (os.path.relpath(ZIP, ROOT), len(manifest["files"]),
           os.path.getsize(ZIP)))
    print("zero_dep:", manifest["zero_dep"])
    print("manifest: %s" % os.path.relpath(os.path.join(PKG, "manifest.json"), ROOT))
    if not manifest["zero_dep"]:
        raise SystemExit("FAILED: third-party import or missing source detected")
    print("PACK OK")

if __name__ == "__main__":
    main()
