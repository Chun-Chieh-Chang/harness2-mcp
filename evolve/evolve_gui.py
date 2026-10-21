#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agnes x Harness^2 -- evolving development console.

A chat-style dev assistant (like Agnes Code) that works in a project folder
with real tools (list / read / write / run shell), and after EVERY completed
task runs a Harness^2-style Propose-Probe-Compose evolution over the
.harness/ scaffolding (systemprompt / tool guidance / guardrails / memory),
so the next task starts from a stronger harness. The system evolves itself.

Pure stdlib. Talks to your Agnes endpoint directly (OpenAI-compatible),
configured in .agns_bridge.env at the repo root.

Launch:   python evolve/evolve_gui.py        (or double-click evolve-gui.bat)
UI:       http://127.0.0.1:8640
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- constants

GUI_PORT = 8640
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROJECT = ROOT / "evolve" / "demo_project"
PROJECT_OVERRIDE_FILE = ROOT / "evolve" / "project_override.txt"
PROJECT = DEFAULT_PROJECT
HARNESS = PROJECT / ".harness"
HARNESS_FILES = ("systemprompt.md", "tool_guidance.md", "guardrails.md", "memory.md")
EXPERIENCE = HARNESS / "experience.jsonl"
VERSION_FILE = HARNESS / "VERSION"
CHAT_URL = None  # computed after env load
MAX_STEPS = 10
OBS_CAP = 1200
_TASK_LOCK = threading.Lock()
_STATE = {"connected": None, "ping_note": ""}


def _refresh_path_globals() -> None:
    global HARNESS, EXPERIENCE, VERSION_FILE
    HARNESS = PROJECT / ".harness"
    EXPERIENCE = HARNESS / "experience.jsonl"
    VERSION_FILE = HARNESS / "VERSION"


def _resolve_project() -> None:
    """Prefer a previously chosen project (persisted by the UI switch)."""
    global PROJECT
    try:
        p = PROJECT_OVERRIDE_FILE.read_text(encoding="utf-8").strip().strip('"')
        if p and Path(os.path.expandvars(p)).is_dir():
            PROJECT = Path(os.path.expandvars(p)).resolve()
    except OSError:
        pass
    _refresh_path_globals()

# ---------------------------------------------------------------- env / Agnes

def _load_env_file() -> None:
    env_file = ROOT / ".agns_bridge.env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file()
_resolve_project()
AGNES_API_URL = os.environ.get("AGNES_API_URL", "")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY", "")
AGNES_MODEL = os.environ.get("AGNES_MODEL", "agnes-3.0-flash")
AGNES_AUTH_HEADER = os.environ.get("AGNES_AUTH_HEADER", "bearer").strip().lower()


def _chat_url() -> str:
    global CHAT_URL
    if CHAT_URL is None:
        url = AGNES_API_URL.rstrip("/")
        if not url:
            raise RuntimeError("AGNES_API_URL is empty -- set it in .agns_bridge.env")
        if not url.endswith(("/chat/completions", "/responses")):
            url += "/chat/completions"
        CHAT_URL = url
    return CHAT_URL


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = AGNES_API_KEY
    if not key:
        raise RuntimeError("AGNES_API_KEY is empty -- set it in .agns_bridge.env")
    if AGNES_AUTH_HEADER == "raw":
        headers["Authorization"] = key
    elif AGNES_AUTH_HEADER == "x-api-key":
        headers["X-Api-Key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    return headers


def model_call(messages, max_tokens=400, temperature=0.2):
    payload = {"model": AGNES_MODEL, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(_chat_url(),
                                         data=json.dumps(payload).encode(),
                                         headers=_auth_headers(), method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read())
            return d["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            if e.code in (401, 403):
                raise RuntimeError(f"Agnes auth failed (HTTP {e.code}): {body}")
            last_err = f"HTTP {e.code}: {body}"
            time.sleep(3)
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(3)
    raise RuntimeError(f"model call failed after retries: {last_err}")


# ---------------------------------------------------------------- harness store

SEED = {
    "systemprompt.md": (
        "# System prompt (Agnes Code, project agent)\n"
        "You are a software-development agent working inside a single project directory.\n"
        "Explore first, change only what is needed, and finish with a short summary.\n"),
    "tool_guidance.md": (
        "# Tool guidance\n"
        "Call exactly ONE tool per turn, as a JSON object:\n"
        "- list_dir {\"path\": \".\"}\n"
        "- read_file {\"path\": \"...\"}\n"
        "- write_file {\"path\": \"...\", \"content\": \"<complete new file>\"}\n"
        "- run_shell {\"cmd\": \"...\"}   (runs in the project dir, 60s limit)\n"
        "- finish {\"summary\": \"...\"}\n"
        "Paths are relative to the project root. write_file replaces the whole file.\n"),
    "guardrails.md": (
        "# Guardrails\n"
        "- Only touch files inside this project.\n"
        "- Never modify .harness/ (the evolution system manages it).\n"),
    "memory.md": (
        "# Project memory\n"
        "(No entries yet.)\n"),
}


def _seed_harness() -> None:
    """Ensure .harness scaffolding exists inside the current PROJECT."""
    if not HARNESS.is_dir():
        HARNESS.mkdir(parents=True, exist_ok=True)
    for name, content in SEED.items():
        p = HARNESS / name
        if not p.is_file():
            p.write_text(content, encoding="utf-8")
    if not VERSION_FILE.is_file():
        VERSION_FILE.write_text("0", encoding="utf-8")
    if not EXPERIENCE.is_file():
        EXPERIENCE.write_text("", encoding="utf-8")


def read_harness() -> dict:
    _seed_harness()
    data = {}
    for name in HARNESS_FILES:
        p = HARNESS / name
        data[name] = p.read_text(encoding="utf-8") if p.is_file() else ""
    try:
        data["version"] = int(VERSION_FILE.read_text(encoding="utf-8").strip() or 0)
    except Exception:
        data["version"] = 0
    return data


def experience_log(limit=15) -> list:
    if not EXPERIENCE.is_file():
        return []
    lines = [l for l in EXPERIENCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for l in lines[-limit:]:
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return list(reversed(out))


# ---------------------------------------------------------------- tools

def _safe_path(rel: str):
    cand = Path(rel) if not Path(rel).is_absolute() else Path(rel)
    target = (PROJECT / rel) if not Path(rel).is_absolute() else Path(rel)
    target = target.resolve()
    proj = PROJECT.resolve()
    if not str(target).startswith(str(proj) + os.sep) and target != proj:
        return None
    h = HARNESS.resolve()
    if target == h or str(target).startswith(str(h) + os.sep):
        return None  # harness dir is reserved for the evolver
    return target


def _tool_list_dir(args):
    base = _safe_path(str(args.get("path", "."))) or PROJECT
    out = []
    for entry in sorted(base.iterdir()) if base.is_dir() else []:
        out.append(entry.name + ("/" if entry.is_dir() else ""))
    return f"dir '{args.get('path', '.')}' -> " + (", ".join(out) or "(empty)")


def _tool_read_file(args):
    p = _safe_path(str(args.get("path", "")))
    if p is None:
        return "ERROR: path outside project or in reserved .harness/ area"
    if not p.is_file():
        return f"ERROR: {args.get('path')} not found"
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:4000] + ("\n...[truncated]" if len(text) > 4000 else "")


def _tool_write_file(args):
    p = _safe_path(str(args.get("path", "")))
    if p is None:
        return "ERROR: path outside project or in reserved .harness/ area"
    content = str(args.get("content", ""))
    if not content:
        return "ERROR: empty content"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {args.get('path')}"


def _tool_run_shell(args):
    cmd = str(args.get("cmd", "")).strip()
    if not cmd:
        return "ERROR: empty command"
    try:
        proc = subprocess.run(cmd, shell=True, cwd=str(PROJECT),
                              capture_output=True, text=True, timeout=60)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        out = out.strip()
        return f"rc={proc.returncode}\n{out[:OBS_CAP]}" + (f"\n...[truncated {len(out)}]" if len(out) > OBS_CAP else "")
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out (60s)"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {type(e).__name__}: {e}"


TOOLS = {
    "list_dir": _tool_list_dir,
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "run_shell": _tool_run_shell,
}


def find_json(text):
    idx = str(text).find("{")
    while idx != -1:
        depth, in_str, esc, end = 0, False, False, -1
        i = idx
        while i < len(text):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            i += 1
        if end > idx:
            try:
                obj = json.loads(text[idx:end + 1])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        idx = text.find("{", idx + 1)
    return None


# ---------------------------------------------------------------- agent loop

def _system_prompt(harness: dict, lessons: list) -> str:
    les = "\n".join(f"- {l}" for l in lessons) if lessons else "(none yet)"
    return (
        f"{harness['systemprompt.md'].strip()}\n\n"
        f"{harness['tool_guidance.md'].strip()}\n\n"
        f"{harness['guardrails.md'].strip()}\n\n"
        f"# Project memory\n{harness['memory.md'].strip()}\n\n"
        f"LESSONS FROM PAST TASKS (apply them silently):\n{les}\n\n"
        "Respond with EXACTLY one JSON object per turn, no prose outside JSON:\n"
        '{"thought":"...","tool":"list_dir|read_file|write_file|run_shell|finish","args":{...}}\n'
        'Examples:\n'
        '{"thought":"explore first","tool":"list_dir","args":{"path":"."}}\n'
        '{"thought":"verify","tool":"run_shell","args":{"cmd":"python run_tests.py"}}\n'
        '{"thought":"done","tool":"finish","args":{"summary":"what changed + how verified"}}\n'
    )


def run_task(task: str) -> dict:
    harness = read_harness()
    version_before = harness["version"]
    lessons = [e.get("lesson", "") for e in experience_log(10) if e.get("lesson")]

    messages = [
        {"role": "system", "content": _system_prompt(harness, lessons)},
        {"role": "user",
         "content": f"TASK: {task}\nPROJECT DIR: {PROJECT.name} (tools run there; paths are relative)"},
    ]

    steps = []
    answer = ""
    ok = False
    malformed = 0
    for step_no in range(1, MAX_STEPS + 1):
        try:
            content = model_call(messages, max_tokens=500, temperature=0.2)
        except Exception as e:  # noqa: BLE001
            answer = f"model error: {e}"
            break
        obj = find_json(content)
        if obj and obj.get("tool") in TOOLS:
            tool = obj["tool"]
            args = obj.get("args") or {}
            obs = TOOLS[tool](args)
            steps.append({"step": step_no, "thought": str(obj.get("thought", ""))[:400],
                          "tool": tool, "args": json.dumps(args, ensure_ascii=False)[:300],
                          "obs": str(obs)[:OBS_CAP], "status": "ok"})
            messages.append({"role": "assistant", "content": content[:1500]})
            messages.append({"role": "user",
                             "content": f"OBSERVATION ({tool} {json.dumps(args, ensure_ascii=False)[:120]}):\n{str(obs)[:800]}\n(next JSON action:)"})
            malformed = 0
        elif obj and str(obj.get("tool", "")).lower() == "finish":
            args = obj.get("args") or {}
            answer = str(args.get("summary") or "done")
            ok = True
            steps.append({"step": step_no, "thought": str(obj.get("thought", ""))[:400],
                          "tool": "finish", "args": json.dumps(args, ensure_ascii=False)[:300],
                          "obs": answer[:OBS_CAP], "status": "ok"})
            break
        else:
            malformed += 1
            steps.append({"step": step_no, "thought": str(content)[:400],
                          "tool": "(none)", "args": "", "obs": "",
                          "status": "malformed" if malformed else "warn"})
            if malformed >= 3:
                answer = "stopped: model produced no valid JSON actions (3 in a row)"
                break
            messages.append({"role": "assistant", "content": content[:1500]})
            messages.append({"role": "user",
                             "content": ("Your last reply was not a single JSON object. "
                                         "Reply with exactly one JSON object: "
                                         '{"thought":"...","tool":"...","args":{...}}')})
        if not answer and step_no == MAX_STEPS:
            answer = "stopped at step cap"
            ok = False
            break
    if not ok and not answer:
        answer = "no finish reached"

    evolution = evolve_task(task, steps, answer, version_before)
    return {
        "ok": ok, "task": task, "answer": answer, "steps": steps,
        "version_before": version_before,
        "evolution": evolution,
    }


# ---------------------------------------------------------------- evolver

def _traj_text(steps: list, answer: str) -> str:
    lines = []
    for s in steps:
        a = s["args"]
        if len(a) > 120:
            a = a[:120] + "…"
        lines.append(f"{s['step']}. [{s['tool']} {a}] -> {s['obs'][:160]}")
    lines.append(f"FINAL: {answer[:400]}")
    return "\n".join(lines)


def evolve_task(task: str, steps: list, answer: str, version_before: int) -> dict:
    harness = read_harness()
    traj = _traj_text(steps, answer)
    prompt = (
        "You are the evolution engine of an agentic harness (Harness^2 style).\n"
        f"TASK JUST COMPLETED: {task}\nTRAJECTORY:\n{traj}\n\n"
        "Current harness snippets:\n"
        f"[guardrails]\n{harness['guardrails.md']}\n[tool_guidance]\n{harness['tool_guidance.md']}\n"
        "Propose the MINIMAL harness revision that helps future similar tasks.\n"
        "Reply with EXACTLY one JSON object (no prose):\n"
        '{"lesson":"one concrete lesson","edits":[{"file":"guardrails.md|tool_guidance.md|memory.md",'
        '"mode":"append_line","text":"..."}]}\n'
        "Rules: at most 3 edits; each text <= 200 chars; never duplicate an existing line; "
        "prefer one lesson + one guardrail line. If nothing to improve, edits may be [].\n"
    )
    edits = []
    lesson = ""
    model_edits_used = False
    try:
        reply = model_call([{"role": "user", "content": prompt}],
                           max_tokens=400, temperature=0.2)
        obj = find_json(reply)
        if obj and isinstance(obj, dict):
            lesson = str(obj.get("lesson", "")).strip()[:300]
            for e in (obj.get("edits") or [])[:3]:
                f = e.get("file", "")
                t = str(e.get("text", "")).strip()
                if f in HARNESS_FILES[:3] and t and len(t) <= 500:
                    edits.append({"file": f, "mode": "append_line", "text": t})
            model_edits_used = bool(edits or lesson)
    except Exception:
        pass

    # deterministic fallback so the system ALWAYS evolves a little
    if not model_edits_used:
        lesson = lesson or f"auto: task '{task[:60]}' done in {len(steps)} steps; keep harness lean."
        g = harness["guardrails.md"]
        if "run the project's tests" not in g:
            edits.append({"file": "guardrails.md",
                         "mode": "append_line",
                         "text": "Always run the project's tests (python run_tests.py) before finishing a code change."})

    # probe (deterministic sanity gate) then compose
    probe = "ok"
    for e in edits:
        p = HARNESS / e["file"]
        cur = p.read_text(encoding="utf-8") if p.is_file() else ""
        if e["text"] in cur:
            e["text"] = ""  # no-op duplicate -> drop
        if len(cur) + len(e["text"]) > 4000:
            probe = f"size cap: {e['file']} would exceed 4000 chars; edit dropped"
            e["text"] = ""
    applied = 0
    for e in edits:
        if not e["text"]:
            continue
        p = HARNESS / e["file"]
        cur = p.read_text(encoding="utf-8") if p.is_file() else ""
        if not cur.endswith("\n"):
            cur += "\n"
        p.write_text(cur + ("- " + e["text"].replace("\n", " ") + "\n"), encoding="utf-8")
        applied += 1

    version_after = version_before + 1
    VERSION_FILE.write_text(str(version_after), encoding="utf-8")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": task[:120], "version_after": version_after,
        "lesson": lesson, "applied_edits": applied, "steps": len(steps),
        "ok": True,
    }
    with open(EXPERIENCE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"version_before": version_before, "version_after": version_after,
            "lesson": lesson, "edits": [e for e in edits if e["text"]],
            "probe": probe, "record": record}


# ---------------------------------------------------------------- http gui

def _gen_results_dir() -> Path:
    return ROOT / "runs" / "agns_demo"


def api_chat(cfg):
    task = str((cfg or {}).get("task", "")).strip()
    if not task:
        return {"ok": False, "output": "請輸入一個任務。"}
    if not _TASK_LOCK.acquire(blocking=False):
        return {"ok": False, "output": "前一個任務還在跑，請等它完成。"}
    t0 = time.time()
    try:
        res = run_task(task)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "task": task, "answer": f"{type(e).__name__}: {e}",
               "steps": [], "version_before": 0,
               "evolution": {"version_after": 0, "lesson": "error", "probe": "", "edits": []}}
    finally:
        _TASK_LOCK.release()
    res["elapsed"] = round(time.time() - t0, 1)
    return {"ok": res["ok"], **res}


def api_ping(cfg):
    try:
        out = model_call([{"role": "user", "content": "Reply with exactly: OK"}],
                         max_tokens=8, temperature=0.0)
        _STATE["connected"] = True
        _STATE["ping_note"] = f"模型 {AGNES_MODEL} 回覆: {out.strip()[:40]}"
        return {"ok": True, "output": _STATE["ping_note"]}
    except Exception as e:  # noqa: BLE001
        _STATE["connected"] = False
        _STATE["ping_note"] = str(e)[:200]
        return {"ok": False, "output": "連不到 Agnes 模型：" + str(e)[:200]}


def api_state(cfg):
    h = read_harness()
    return {
        "ok": True,
        "version": h["version"],
        "model": AGNES_MODEL,
        "connected": _STATE["connected"],
        "ping_note": _STATE["ping_note"],
        "project": PROJECT.name,
        "project_path": str(PROJECT),
        "default_project_path": str(DEFAULT_PROJECT),
        "files": {k: h[k] for k in HARNESS_FILES},
        "experience": experience_log(12),
    }


def api_reset(cfg):
    # reset evolution only (keep project code)
    _seed_harness()
    for name in HARNESS_FILES:
        (HARNESS / name).write_text(SEED[name], encoding="utf-8")
    VERSION_FILE.write_text("0", encoding="utf-8")
    EXPERIENCE.write_text("", encoding="utf-8")
    return {"ok": True, "output": "已重置進化狀態（harness 回到 v0；專案程式碼保留）。"}


def api_switch_project(cfg):
    """Point the console at a different project directory (persisted).

    Empty / "default" -> switch back to the bundled demo project and clear
    the persisted override, so the next bat double-click uses the demo again.
    """
    global PROJECT
    raw = str((cfg or {}).get("path", "")).strip().strip('"')
    if raw.lower() in ("", "default"):
        target = DEFAULT_PROJECT
        PROJECT = target.resolve()
        _refresh_path_globals()
        _seed_harness()
        try:
            PROJECT_OVERRIDE_FILE.unlink()
        except OSError:
            pass
        return {"ok": True,
                "output": (f"已切回內建 demo 專案：{target}\n"
                           f"（已清除「記住專案」；下次雙擊 bat 會用 demo）")}
    target = Path(os.path.expandvars(raw)).expanduser()
    if not target.is_dir():
        return {"ok": False,
                "output": f"這個路徑不是資料夾：{target}\n請在資源管理器複製資料夾完整路徑再貼上。"}
    target = target.resolve()
    PROJECT = target
    _refresh_path_globals()
    _seed_harness()
    try:
        PROJECT_OVERRIDE_FILE.write_text(str(target), encoding="utf-8")
        persisted = True
    except OSError:
        persisted = False
    return {"ok": True,
            "output": (f"已切換到專案：{target}\n"
                       f"（.harness 已確保存在；進化狀態從 v0 重新開始，已持久化，"
                       f"下次雙擊 bat 會自動沿用此專案）" if not persisted
                       else f"已切換並記住專案：{target}\n"
                            f"（.harness 已確保存在；進化從 v0 開始；下次雙擊 bat 自動沿用）")}

_ACTIONS = {
    "chat": api_chat,
    "ping": api_ping,
    "state": api_state,
    "reset": api_reset,
    "switch_project": api_switch_project,
}

HTML = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agnes 進化開發台</title>
<style>
 body{font-family:"Microsoft JhengHei","PingFang TC",sans-serif;background:#0b1220;color:#e2e8f0;margin:0;height:100vh;display:flex;flex-direction:column}
 header{padding:10px 16px;background:#0f172a;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 header h1{font-size:16px;margin:0}
 .badge{font-size:12px;padding:3px 10px;border-radius:99px;background:#1e293b;color:#94a3b8}
 .badge.on{background:#14532d;color:#86efac}.badge.off{background:#450a0a;color:#fca5a5}
 main{flex:1;display:flex;min-height:0}
 .chat{flex:1.6;display:flex;flex-direction:column;min-width:0;border-right:1px solid #1e293b}
 .msgs{flex:1;overflow-y:auto;padding:14px}
 .m{margin:0 0 10px;padding:10px 12px;border-radius:10px;font-size:14px;line-height:1.5;white-space:pre-wrap}
 .m.user{background:#1d4ed8;color:#fff;max-width:75%}
 .m.ai{background:#111c2e;border:1px solid #1e293b}
 .m .th{font-size:12px;color:#64748b}
 .m details{margin:4px 0;font-size:12px;color:#94a3b8}
 .m details pre{background:#0f172a;padding:8px;border-radius:6px;white-space:pre-wrap;font-size:12px;max-height:220px;overflow:auto}
 .m .ans{background:#052e1b;border:1px solid #14532d;padding:8px 10px;border-radius:8px;margin-top:6px;color:#bbf7d0;font-size:13px;white-space:pre-wrap}
 .evo{margin-top:6px;background:#1e1b4b;border:1px solid #4338ca;padding:8px 10px;border-radius:8px;font-size:13px;color:#c7d2fe}
 .inbar{display:flex;gap:8px;padding:10px;border-top:1px solid #1e293b;background:#0f172a}
 .inbar input{flex:1;background:#111c2e;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px;font-size:14px}
 .inbar button{background:#2563eb;border:0;color:#fff;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
 .inbar button:disabled{opacity:.5}
 .panel{flex:1;min-width:320px;max-width:420px;overflow-y:auto;padding:14px;background:#0f172a}
 .panel h2{font-size:14px;color:#94a3b8;margin:14px 0 6px}
 .ver{font-size:34px;font-weight:700;color:#86efac}
 .exp{font-size:12px;background:#111c2e;border:1px solid #1e293b;border-radius:8px;padding:8px;margin:6px 0;color:#cbd5e1;white-space:pre-wrap}
 .exp b{color:#fbbf24}
 pre.file{background:#020617;border:1px solid #1e293b;border-radius:8px;padding:8px;font-size:12px;color:#94a3b8;white-space:pre-wrap;max-height:240px;overflow:auto}
 .small{font-size:11px;color:#64748b}
 .btnrow button{background:#334155;font-size:12px;padding:6px 10px;margin:4px 6px 0 0}
 .projbar{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
 .projbar label{font-size:12px;color:#94a3b8}
 .projbar input{width:100%;box-sizing:border-box;background:#111c2e;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:8px;font-size:13px}
 .projbar .brow{display:flex;gap:8px}
 .projbar button{flex:1;background:#1e293b;border:1px solid #334155;color:#cbd5e1;border-radius:8px;padding:8px;font-size:12px;cursor:pointer}
 .projbar button:hover{background:#334155}
 .projnote{font-size:11px;color:#64748b}
</style></head><body>
<header>
 <h1>Agnes × Harness² 進化開發台</h1>
 <span class="badge" id="mbadge">模型連線：檢查中…</span>
 <span class="badge" id="vbadge">harness v?</span>
 <span class="badge off" id="ebadge">…</span>
</header>
<main>
 <section class="chat">
  <div class="msgs" id="msgs">
   <div class="m ai"><span class="th">用法：輸入一個開發任務（例如「在 calc.py 實作 discount(price, pct) 並加單元測試」）。</span><br>
   我會在 demo_project 裡用工具實際執行；完成後自動進化 harness（下一題變強），右側可看進化歷史與當前 harness。</div>
  </div>
  <div class="inbar">
   <input id="task" placeholder="開發任務，例如：在 calc.py 新增 compound(a, n) 函式並補測試">
   <button id="go" onclick="send()">執行</button>
  </div>
 </section>
 <aside class="panel">
<div class="projbar">
    <label>專案路徑（貼上你自己的資料夾，切換後立即生效並記住）</label>
    <input id="projpath" placeholder="例：D:\work\myapp   或   按「用內建 demo」">
    <div class="brow">
      <button onclick="switchProj()">切換到我的專案</button>
      <button onclick="switchDefault()">用內建 demo</button>
    </div>
    <div class="projnote" id="projnote">目前專案：<span id="projcur">…</span>（.harness 進化狀態存在此專案內）</div>
  </div>

  <h2>當前 harness 版本</h2>
  <div class="ver" id="ver">v?</div>
  <div class="small">每完成一題，evolution engine 會自動修訂 .harness/（systemprompt、工具指南、護欄、記憶），VERSION +1。</div>
  <h2>進化歷史</h2>
  <div id="exp"></div>
  <h2>當前 harness 檔案</h2>
  <div id="files"></div>
  <div class="btnrow">
   <button onclick="api('ping').then(d=>{renderState(); })">檢查模型連線</button>
   <button onclick="if(confirm('重置進化狀態到 v0？(專案程式碼保留)'))api('reset').then(d=>{renderState();addSys(d.output);})">重置到 v0</button>
  </div>
 </aside>
</main>
<script>
async function api(name, payload){
  const r = await fetch('/api/'+name, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload||{})});
  return await r.json();
}
function addSys(t){
  const d=document.createElement('div'); d.className='m ai';
  d.innerHTML='<span class="th">system</span>\n'+t; document.getElementById('msgs').appendChild(d); scroll();
}
function scroll(){const m=document.getElementById('msgs');m.scrollTop=m.scrollHeight;}
function addMsg(cls, html){
  const d=document.createElement('div'); d.className='m '+cls; d.innerHTML=html;
  document.getElementById('msgs').appendChild(d); scroll();
}
async function send(){
  const t=document.getElementById('task').value.trim(); if(!t) return;
  addMsg('user', t.replace(/</g,'&lt;'));
  document.getElementById('task').value='';
  const b=document.getElementById('go'); b.disabled=true; b.textContent='執行中…';
  addMsg('ai','<span class="th">執行中…（每一步會即時顯示工具動作）</span>');
  const busyEl=document.getElementById('msgs').lastChild;
  const d=await api('chat',{task:t});
  busyEl.remove();
  // render steps
  let h='<span class="th">工具軌跡（'+d.steps.length+' 步，'+(d.elapsed||0)+' 秒）</span>';
  for(const s of d.steps){
    h+='\n<details'+(s.status==='ok'?'':'')+'><summary>步'+s.step+' '+s.tool+(s.args&&s.args!==' '?' '+s.args.slice(0,60):'')+(s.status!=='ok'?' ['+s.status]':'')+'</summary><pre>'
      + (s.thought?'Thought: '+s.thought+'\n':'') + 'OBS:\n'+(s.obs||'(no obs)') +'</pre></details>';
  }
  h+='\n<div class="ans">'+ (d.ok?'✅ ':'⚠️ ') + escapeHtml(d.answer||'') +'</div>';
  if(d.evolution && d.evolution.version_after){
    const e=d.evolution;
    h+='\n<div class="evo">🧬 已進化 harness <b>v'+e.version_before+' → v'+e.version_after+'</b>'
      + (e.lesson?'<br>教訓：'+escapeHtml(e.lesson):'')
      + (e.edits&&e.edits.length?'<br>修訂：'+e.edits.map(x=>x.file+' +1行').join('、'):'')
      + (e.probe&&e.probe!=='ok'? '<br>probe: '+escapeHtml(e.probe):'') +'</div>';
  }
  addMsg('ai', h);
  b.disabled=false; b.textContent='執行';
  renderState();
}
function escapeHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
async function renderState(){
  const d=await api('state');
  document.getElementById('vbadge').textContent='harness v'+d.version;
  document.getElementById('projcur').textContent=d.project_path;
  document.getElementById('projnote').innerHTML='目前專案：<b>'+escapeHtml(d.project_path)+'</b>'+ (d.project_path===d.default_project_path ? '（內建 demo）' : '（你的專案，已記住）');
  document.getElementById('ver').textContent='v'+d.version;
  const c=document.getElementById('mbadge');
  if(d.connected===true){c.textContent='模型 '+d.model+' 已連線';c.className='badge on';}
  else if(d.connected===false){c.textContent='模型未連線：'+d.ping_note;c.className='badge off';}
  else {c.textContent='模型 '+d.model;c.className='badge';}
  const e=document.getElementById('ebadge');
  e.textContent='歷史 '+d.experience.length+' 筆進化'; e.className='badge on';
  document.getElementById('exp').innerHTML = d.experience.map(x=>
    '<div class="exp"><b>v'+x.version_after+'</b> '+escapeHtml((x.task||'').slice(0,50))
    +'<br>'+escapeHtml(x.lesson||'')+'</div>').join('') || '<div class="exp small">（尚無進化記錄）</div>';
  document.getElementById('files').innerHTML = Object.keys(d.files).map(f=>
    '<details style="margin:6px 0"><summary class="small">'+f+' ('+d.files[f].length+' 字元)</summary><pre class="file">'+escapeHtml(d.files[f])+'</pre></details>').join('');
}
async function switchProj(){
  const p=document.getElementById('projpath').value.trim();
  if(!p){ addSys('請先輸入專案路徑。'); return; }
  const d=await api('switch_project',{path:p});
  addSys(d.output); renderState();
}
async function switchDefault(){
  document.getElementById('projpath').value='';
  const d=await api('switch_project',{path:''});
  addSys(d.output||'switching to built-in demo'); renderState();
}
window.addEventListener('load', ()=>{ api('ping').then(renderState); document.getElementById('task').focus(); });
document.getElementById('task').addEventListener('keydown', e=>{ if(e.key==='Enter') send(); });
</script>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            cfg = json.loads(raw or b"{}")
        except Exception:
            cfg = {}
        action = _ACTIONS.get(self.path.lstrip("/").split("/", 1)[-1])
        if action is None:
            self._send(404, json.dumps({"ok": False, "output": "unknown api"}).encode(),
                       "application/json; charset=utf-8")
            return
        try:
            res = action(cfg)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "output": f"{type(e).__name__}: {e}",
                   "trace": traceback.format_exc()[-800:]}
        self._send(200, json.dumps(res, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


def main():
    # Seed .harness scaffolding in whichever project we're pointing at.
    _seed_harness()
    # Starter files (calc.py etc.) only exist for the bundled demo project.
    if str(PROJECT) == str(DEFAULT_PROJECT) and not (PROJECT / "calc.py").is_file():
        _write_demo_project()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", GUI_PORT), Handler)
    print("=" * 62)
    print("Agnes x Harness^2 進化開發台")
    print(f"  UI      : http://127.0.0.1:{GUI_PORT}")
    print(f"  project : {PROJECT}")
    print(f"  model   : {AGNES_MODEL} @ {AGNES_API_URL or '(unset)'}")
    print("  Ctrl+C 停止")
    print("=" * 62)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{GUI_PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _write_demo_project():
    (PROJECT / "calc.py").write_text(
        '"""Tiny calculator library."""\n\n'
        "def add(a, b):\n    return a + b\n\n"
        "def mul(a, b):\n    return a * b\n\n"
        "def avg(nums):\n"
        "    if not nums:\n"
        "        raise ValueError(\"avg() of empty sequence\")\n"
        "    return sum(nums) / len(nums)\n\n"
        "def discount(price, pct):\n"
        '    """Return price reduced by pct percent. (Not implemented yet.)"""\n'
        "    raise NotImplementedError\n",
        encoding="utf-8")
    (PROJECT / "test_calc.py").write_text(
        "import unittest\nfrom calc import add, mul, avg, discount\n\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
        "    def test_mul(self):\n        self.assertEqual(mul(4, 5), 20)\n"
        "    def test_avg(self):\n        self.assertAlmostEqual(avg([1, 2, 3]), 2.0)\n"
        "    # TODO: add tests for discount()\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n",
        encoding="utf-8")
    (PROJECT / "run_tests.py").write_text(
        "import unittest\n\n"
        "suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')\n"
        "r = unittest.TextTestRunner(verbosity=2).run(suite)\n"
        "raise SystemExit(0 if r.wasSuccessful() else 1)\n",
        encoding="utf-8")
    (PROJECT / "README.md").write_text(
        "# demo project\n\nTiny calculator library + unittest suite.\n"
        "Run tests: `python run_tests.py`\n",
        encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
