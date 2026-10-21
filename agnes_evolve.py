#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Agnes x Harness^2 — evolving dev agent (terminal, layers on your IDE).

Usage:
  cd D:\work\myproject
  python C:\path\to\agnes_evolve.py "add discount() to calc.py and add a test"

What happens:
  1. Agent runs in YOUR project directory (CWD).
  2. After the task, it evolves .harness/ (guardrails, tool guidance, memory)
     so the next task starts stronger.
  3. Your IDE shows all file changes (git diff, editor refresh, etc.).
  4. No browser. No separate app. Just a terminal command in your existing workflow.

Config: reads .agns_bridge.env from your project (or a known repo path):
  AGNES_API_URL, AGNES_API_KEY, AGNES_MODEL, AGNES_AUTH_HEADER

Pure stdlib. Python 3.10+.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- config

def _find_env_file() -> Path | None:
    """Walk up from CWD to find .agns_bridge.env (or use known repo paths)."""
    here = Path.cwd()
    for i in range(8):
        cand = here / ".agns_bridge.env"
        if cand.is_file():
            return cand
        here = here.parent
    for r in (r"E:\Self-developed_Apps\G3\harness2",
              r"C:\Users\USER\.agnes\temporary\2026-10-19\20261019_1\work\harness2"):
        cand = Path(r) / ".agns_bridge.env"
        if cand.is_file():
            return cand
    return None


def _load_config() -> dict:
    env = {}
    cfg_file = _find_env_file()
    if cfg_file:
        for line in cfg_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    for k in ("AGNES_API_URL", "AGNES_API_KEY", "AGNES_MODEL", "AGNES_AUTH_HEADER"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


CFG = _load_config()
API_URL = CFG.get("AGNES_API_URL", "").rstrip("/")
API_KEY = CFG.get("AGNES_API_KEY", "")
MODEL = CFG.get("AGNES_MODEL", "agnes-3.0-flash")
AUTH = CFG.get("AGNES_AUTH_HEADER", "raw").lower()

# ---------------------------------------------------------------- model call

def model_call(messages: list, max_tokens: int = 500, temperature: float = 0.2) -> str:
    url = API_URL if API_URL.endswith(("/chat/completions", "/responses")) else API_URL + "/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if AUTH == "raw":
        headers["Authorization"] = API_KEY
    elif AUTH == "x-api-key":
        headers["X-Api-Key"] = API_KEY
    else:
        headers["Authorization"] = "Bearer " + API_KEY
    payload = {"model": MODEL, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    last_err = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            if e.code in (401, 403):
                raise RuntimeError(f"Agnes auth failed (HTTP {e.code}): {body}\n"
                                   f"Check AGNES_API_KEY / AGNES_AUTH_HEADER in .agns_bridge.env")
            last_err = f"HTTP {e.code}: {body}"
            time.sleep(3)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(3)
    raise RuntimeError(f"model call failed: {last_err}")

# ---------------------------------------------------------------- harness

PROJECT = Path.cwd().resolve()
HARNESS = PROJECT / ".harness"
HARNESS_FILES = ("systemprompt.md", "tool_guidance.md", "guardrails.md", "memory.md")
EXPERIENCE = HARNESS / "experience.jsonl"
VERSION_FILE = HARNESS / "VERSION"

SEED = {
    "systemprompt.md": (
        "# System prompt\n"
        "You are a software-development agent working in the project directory.\n"
        "Explore first, change only what is needed, verify with tests, finish with a summary.\n"),
    "tool_guidance.md": (
        "# Tool guidance\n"
        "Call exactly ONE tool per turn as a JSON object:\n"
        '{"thought":"...","tool":"list_dir|read_file|write_file|run_shell|finish","args":{...}}\n'
        "- list_dir {\"path\": \".\"}\n"
        "- read_file {\"path\": \"src/main.py\"}\n"
        "- write_file {\"path\": \"src/main.py\", \"content\": \"<complete file>\"}\n"
        "- run_shell {\"cmd\": \"python -m pytest\"}   (60s limit, runs in project root)\n"
        "- finish {\"summary\": \"what changed, how verified\"}\n"
        "Paths are relative to the project root. write_file replaces the whole file.\n"),
    "guardrails.md": (
        "# Guardrails\n"
        "- Only modify files in this project.\n"
        "- Never modify .harness/ (evolution system manages it).\n"
        "- Run tests before finishing code changes.\n"),
    "memory.md": ("# Project memory\n(No entries yet.)\n"),
}


def ensure_harness() -> None:
    if not HARNESS.is_dir():
        HARNESS.mkdir()
        for name, content in SEED.items():
            (HARNESS / name).write_text(content, encoding="utf-8")
    if not VERSION_FILE.is_file():
        VERSION_FILE.write_text("0", encoding="utf-8")
    if not EXPERIENCE.is_file():
        EXPERIENCE.write_text("", encoding="utf-8")


def read_harness() -> dict:
    ensure_harness()
    data = {}
    for name in HARNESS_FILES:
        p = HARNESS / name
        data[name] = p.read_text(encoding="utf-8") if p.is_file() else SEED.get(name, "")
    data["version"] = int(VERSION_FILE.read_text(encoding="utf-8").strip() or 0)
    return data


def experience_lessons(limit=10) -> list[str]:
    if not EXPERIENCE.is_file():
        return []
    lines = [l for l in EXPERIENCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for l in lines[-limit:]:
        try:
            out.append(json.loads(l).get("lesson", ""))
        except Exception:
            pass
    return [x for x in out if x]

# ---------------------------------------------------------------- tools

def safe_path(rel: str) -> Path | None:
    target = (PROJECT / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    if not str(target).startswith(str(PROJECT)):
        return None
    h = HARNESS.resolve()
    if target == h or str(target).startswith(str(h) + os.sep):
        return None
    return target


def tool_list_dir(args: dict) -> str:
    p = safe_path(str(args.get("path", "."))) or PROJECT
    if not p.is_dir():
        return f"ERROR: {args.get('path')} not a directory"
    items = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
    return f"dir '{args.get('path')}': " + (", ".join(items[:50]) or "(empty)")


def tool_read_file(args: dict) -> str:
    p = safe_path(str(args.get("path", "")))
    if p is None:
        return "ERROR: path outside project or in .harness/"
    if not p.is_file():
        return f"ERROR: {args.get('path')} not found"
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:4000] + ("\n...[truncated]" if len(text) > 4000 else "")


def tool_write_file(args: dict) -> str:
    p = safe_path(str(args.get("path", "")))
    if p is None:
        return "ERROR: path outside project or in .harness/"
    content = str(args.get("content", ""))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars -> {args.get('path')}"


def tool_run_shell(args: dict) -> str:
    cmd = str(args.get("cmd", "")).strip()
    if not cmd:
        return "ERROR: empty command"
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(PROJECT),
                           capture_output=True, text=True, timeout=60)
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        out = out.strip()
        return f"rc={r.returncode}\n{out[:1500]}" + (f"\n...[truncated {len(out)}]" if len(out) > 1500 else "")
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out (60s)"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


TOOLS = {"list_dir": tool_list_dir, "read_file": tool_read_file,
         "write_file": tool_write_file, "run_shell": tool_run_shell}

# ---------------------------------------------------------------- JSON extraction

def find_json(text: str) -> dict | None:
    idx = text.find("{")
    while idx != -1:
        depth, in_str, esc, end = 0, False, False, -1
        i = idx
        while i < len(text):
            c = text[i]
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': in_str = False
            else:
                if c == '"': in_str = True
                elif c == "{": depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0: end = i; break
            i += 1
        if end > idx:
            try:
                obj = json.loads(text[idx:end + 1])
                if isinstance(obj, dict): return obj
            except Exception: pass
        idx = text.find("{", idx + 1)
    return None

# ---------------------------------------------------------------- agent loop

def run_task(task: str) -> dict:
    harness = read_harness()
    v0 = harness["version"]
    lessons = experience_lessons(10)

    system = (
        f"{harness['systemprompt.md'].strip()}\n\n"
        f"{harness['tool_guidance.md'].strip()}\n\n"
        f"{harness['guardrails.md'].strip()}\n\n"
        f"# Project memory\n{harness['memory.md'].strip()}\n\n"
        + (f"LESSONS FROM PAST TASKS:\n" + "\n".join(f"- {l}" for l in lessons) + "\n\n" if lessons else "")
        + "Respond with EXACTLY one JSON object per turn.\n"
        '{"thought":"...","tool":"list_dir|read_file|write_file|run_shell|finish","args":{...}}\n'
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"TASK: {task}\nPROJECT: {PROJECT.name} (paths relative, tools run in project root)"},
    ]

    steps: list[dict] = []
    answer = ""
    ok = False
    malformed = 0

    for step_no in range(1, 15):
        try:
            content = model_call(messages, max_tokens=500)
        except Exception as e:
            answer = f"model error: {e}"
            break

        obj = find_json(content)
        if obj and obj.get("tool") in TOOLS:
            tool = obj["tool"]
            args = obj.get("args") or {}
            obs = TOOLS[tool](args)
            steps.append({"step": step_no, "tool": tool,
                          "args": json.dumps(args, ensure_ascii=False)[:200],
                          "obs": str(obs)[:600], "thought": str(obj.get("thought", ""))[:200]})
            print(f"  [{step_no}] {tool}({json.dumps(args, ensure_ascii=False)[:80]})")
            messages.append({"role": "assistant", "content": content[:1200]})
            messages.append({"role": "user",
                             "content": f"OBS ({tool}):\n{str(obs)[:600]}\n(next JSON action:)"})
            malformed = 0
        elif obj and str(obj.get("tool", "")).lower() == "finish":
            args = obj.get("args") or {}
            answer = str(args.get("summary", "done"))
            ok = True
            steps.append({"step": step_no, "tool": "finish",
                          "args": json.dumps(args, ensure_ascii=False)[:200],
                          "obs": answer[:400], "thought": str(obj.get("thought", ""))[:200]})
            print(f"  [{step_no}] finish -> {answer[:120]}")
            break
        else:
            malformed += 1
            if malformed >= 3:
                answer = "stopped: 3 consecutive malformed responses"
                break
            messages.append({"role": "assistant", "content": content[:1200]})
            messages.append({"role": "user",
                             "content": "Reply with one JSON object only: {\"thought\":...,\"tool\":...,\"args\":...}"})

    if not ok and not answer:
        answer = "stopped at step cap (14)"
    return {"ok": ok, "task": task, "answer": answer, "steps": steps,
            "version_before": v0, "project": str(PROJECT)}

# ---------------------------------------------------------------- evolution

def evolve(task: str, steps: list, answer: str, v0: int) -> dict:
    harness = read_harness()
    traj = "\n".join(
        f"{s['step']}. [{s['tool']} {s['args']}] -> {s['obs'][:120]}" for s in steps
    ) + f"\nFINAL: {answer[:300]}"

    prompt = (
        f"Evolution engine. TASK: {task}\nTRAJ:\n{traj}\n\n"
        f"Current guardrails:\n{harness['guardrails.md']}\n"
        f"Current tool guidance:\n{harness['tool_guidance.md']}\n\n"
        "Propose MINIMAL revision. Reply EXACTLY one JSON:\n"
        '{"lesson":"one concrete takeaway","edits":[{"file":"guardrails.md|tool_guidance.md|memory.md",'
        '"mode":"append_line","text":"..."}]}\n'
        "Rules: <=3 edits, each <=200 chars, no duplicates. If nothing to add, edits=[]."
    )
    lesson = ""
    edits: list[dict] = []
    try:
        reply = model_call([{"role": "user", "content": prompt}], max_tokens=400, temperature=0.2)
        obj = find_json(reply)
        if obj and isinstance(obj, dict):
            lesson = str(obj.get("lesson", "")).strip()[:300]
            for e in (obj.get("edits") or [])[:3]:
                f = e.get("file", "")
                t = str(e.get("text", "")).strip()
                if f in HARNESS_FILES and t:
                    edits.append({"file": f, "text": t})
    except Exception:
        pass

    if not edits:
        g = harness["guardrails.md"]
        if "run tests before finishing" not in g.lower():
            lesson = lesson or "Always verify with tests before declaring success."
            edits.append({"file": "guardrails.md",
                         "text": "Always verify with tests (run the project's test command) before finishing."})

    applied = 0
    for e in edits:
        p = HARNESS / e["file"]
        cur = p.read_text(encoding="utf-8") if p.is_file() else ""
        if e["text"] in cur:
            continue
        if not cur.endswith("\n"):
            cur += "\n"
        p.write_text(cur + f"- {e['text']}\n", encoding="utf-8")
        applied += 1

    v1 = v0 + 1
    VERSION_FILE.write_text(str(v1), encoding="utf-8")
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "task": task[:120], "version": v1, "lesson": lesson,
              "edits": applied, "steps": len(steps)}
    with open(EXPERIENCE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"version_before": v0, "version_after": v1,
            "lesson": lesson, "edits_applied": applied}

# ---------------------------------------------------------------- main

def main() -> int:
    if not API_URL or not API_KEY:
        print("ERROR: AGNES_API_URL / AGNES_API_KEY not set.")
        print(f"  Searched env file: {_find_env_file()}")
        print("  Put .agns_bridge.env next to your project, or set env vars.")
        return 1

    if len(sys.argv) < 2:
        print(f"Agnes evolving dev agent | project: {PROJECT.name} | model: {MODEL}")
        print("Usage:  python agnes_evolve.py \"your task\"")
        print("  e.g.  python agnes_evolve.py \"add a discount function to calc.py and add a unit test\"")
        task = input("\nTask: ").strip()
        if not task:
            print("No task given. Exiting.")
            return 0
    else:
        task = " ".join(sys.argv[1:]).strip()

    print(f"\n{'='*60}")
    print(f"  Project : {PROJECT}")
    print(f"  Model   : {MODEL} @ {API_URL}")
    print(f"  Task    : {task}")
    print(f"{'='*60}\n")

    t0 = time.time()
    result = run_task(task)

    print(f"\n{'─'*60}")
    print(f"  Result  : {'✅' if result['ok'] else '⚠️'} {result['answer'][:120]}")
    print(f"  Steps   : {len(result['steps'])}")
    print(f"  Time    : {time.time()-t0:.1f}s")
    print(f"{'─'*60}")

    evo = evolve(task, result["steps"], result["answer"], result["version_before"])
    print(f"\n  🧬 Evolved harness v{evo['version_before']} → v{evo['version_after']}")
    if evo["lesson"]:
        print(f"     lesson: {evo['lesson'][:100]}")
    if evo["edits_applied"]:
        print(f"     edits : {evo['edits_applied']} line(s) added to .harness/")
    print(f"     Next task will start from v{evo['version_after']} with accumulated lessons.")
    print(f"\n  File changes in {PROJECT.name}/ — open in your IDE / git diff to review.")
    print(f"{'='*60}\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
