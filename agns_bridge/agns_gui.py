# -*- coding: utf-8 -*-
"""Agnes x Harness^2 desktop GUI -- stdlib only, no install.

Launch:  python agnes_bridge/agns_gui.py     (or double-click agns-gui.bat)
Then a browser opens http://127.0.0.1:8630  with three button groups:
  (1) run the demo with the built-in worker or a real AGNES_CLI
  (2) start the local OpenAI-compatible bridge + test the Agnes link
  (3) show / open the latest demo results
All config comes from .agns_bridge.env at the repo root.
"""

import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GUI_PORT = 8630
BRIDGE_MODULE = HERE / "agnes_openai_proxy.py"
RESULTS_JSON = ROOT / "runs" / "agns_demo" / "agns_demo.json"


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

# Make the source tree importable without a pip install (the `harness2`
# package lives right inside ROOT), and tolerate a pip-install fallback.
sys.path.insert(0, str(ROOT))
try:
    import harness2  # noqa: F401
except Exception:
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

_STATE = {"bridge_srv": None, "bridge_proc": None}


def _run_demo(cfg: dict) -> dict:
    use_cli = bool(cfg.get("use_cli"))
    cli = (cfg.get("cli") or "").strip()
    try:
        k = max(1, min(5, int(cfg.get("k") or 1)))
    except (TypeError, ValueError):
        k = 1
    env = dict(os.environ)
    env.pop("AGNES_CLI", None)
    if use_cli:
        if not cli:
            return {"ok": False,
                    "output": "没有填 AGNES_CLI。請在输入框填指令（例：python agnes_bridge\\fake_agnes_cli_example.py）"
                              "或改按「①-A 内置 worker」。"}
        env["AGNES_CLI"] = cli
    cmd = [sys.executable, "-m", "harness2.cli.agns_demo",
           "--output", "runs/agns_demo", "--k", str(k), "--mode", "both"]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "超時：900 秒内没跑完。請减小 k 再試。"}
    out = (proc.stdout or "").strip()
    if proc.stderr and proc.stderr.strip():
        out += "\n" + proc.stderr.strip()
    return {"ok": proc.returncode == 0,
            "output": out[-4000:] or "(no output)",
            "note": f"耗時 {time.time() - t0:.0f} 秒"}



def _load_bridge_ns() -> dict:
    """Return the bridge module's namespace (in-process, reliable).

    Tries, in order:
      1. importlib.import_module('agns_bridge.agnes_openai_proxy')
      2. exec the source found by walking HERE / ROOT
    Returns the module dict on success, {} on failure.
    """
    import importlib

    try:
        mod = importlib.import_module("agns_bridge.agnes_openai_proxy")
        return mod.__dict__
    except Exception:
        pass

    bridge_src = None
    for base in (HERE, ROOT):
        try:
            direct = base / "agnes_openai_proxy.py"
            if direct.is_file():
                bridge_src = direct.read_text(encoding="utf-8")
                break
        except Exception:
            pass
        if bridge_src:
            break
    if bridge_src is None:
        for base in (HERE, ROOT):
            try:
                for r, _, fs in os.walk(base):
                    for fn in fs:
                        if fn == "agnes_openai_proxy.py":
                            with open(os.path.join(r, fn), encoding="utf-8") as fh:
                                bridge_src = fh.read()
                            break
                    if bridge_src:
                        break
            except Exception:
                continue
            if bridge_src:
                break

    if bridge_src is None:
        return {}
    import types
    ns = types.ModuleType("agns_proxy")
    exec(compile(bridge_src, "agnes_openai_proxy.py", "exec"), ns)
    return ns


def _start_bridge(cfg: dict) -> dict:
    if _STATE["bridge_srv"] is not None:
        host, port = _STATE["bridge_srv"].server_address
        return {"ok": True,
                "output": f"Bridge 已经在跑：http://{host}:{port}/v1"}
    ns = _load_bridge_ns()
    if not ns:
        return {"ok": False,
                "output": "无法载入 agnes_openai_proxy.py（請确認 agnes_bridge 目录完整）。"}
    try:
        srv = http.server.ThreadingHTTPServer((ns["HOST"], ns["PORT"]), ns["Handler"])
    except OSError as exc:
        return {"ok": False,
                "output": f"Bridge 啟動失败：{exc}（請确認 AGNES_PROXY_PORT 未被占用）"}
    _STATE["bridge_srv"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return {"ok": True,
            "output": (f"Bridge 已啟動：http://{ns['HOST']}:{ns['PORT']}/v1\n"
                       f"上游 Agnes 端點：{ns.get('API_URL') or '(未设定)'}"
                       f"（auth: {ns.get('AUTH_HEADER', 'bearer')}），"
                       f"model: {ns.get('DEFAULT_MODEL', '(未设定)')}"),
            "note": "现在可以按「测試 Agnes 連线」了"}


def _probe_bridge() -> str:
    """Find a reachable bridge endpoint, or '' if none."""
    host = os.environ.get("AGNES_PROXY_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("AGNES_PROXY_PORT", "8620") or 8620)
    except (TypeError, ValueError):
        port = 8620
    target = _STATE.get("bridge_srv")
    if target is not None:
        host, port = target.server_address
        port = int(port)
    import socket
    seen = set()
    for h, p in ((host, port), ("127.0.0.1", port), ("127.0.0.1", 8620)):
        if (h, p) in seen:
            continue
        seen.add((h, p))
        s = socket.socket()
        s.settimeout(0.4)
        try:
            s.connect((h, p))
            s.close()
            return f"http://{h}:{p}"
        except OSError:
            continue
    return ""


def _test_link(cfg: dict) -> dict:
    base = _probe_bridge()
    if not base:
        return {"ok": False,
                "output": "Bridge 還没在跑。請先按「②-A 啟動 Bridge」，或另開终端跑 "
                          "python -m agnes_bridge.agnes_openai_proxy 再按本钮。"}
    payload = {
        "model": os.environ.get("AGNES_MODEL", "agnes-3.0-flash"),
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8,
    }
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "agnes-bridge"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
            content = json.dumps(
                d.get("choices", [{}])[0].get("message", {}).get("content", ""),
                ensure_ascii=False)
            return {"ok": True,
                    "output": (f"連线成功！Agnes 模型回覆：{content}\n"
                               f"用量：{json.dumps(d.get('usage', {}))}"),
                    "note": f"Harness^2 现在可以透过 {base}/v1 调用 Agnes"}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        hint = ""
        if exc.code == 401:
            hint = "\n→ 401：API key 或 AGNES_AUTH_HEADER 不对，請检查 .agns_bridge.env。"
        elif exc.code == 503:
            hint = "\n→ 503：AGNES_API_URL 未设定。"
        return {"ok": False, "output": f"Agnes 端點回覆 HTTP {exc.code}：{body[:300]}{hint}"}
    except Exception as exc:
        return {"ok": False, "output": f"連不到 bridge（{base}）：{type(exc).__name__}: {exc}"}


def _show_results(cfg: dict) -> dict:
    if not RESULTS_JSON.is_file():
        return {"ok": False, "output": "還没有结果。請先按「① 跑 Demo」。"}
    d = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    lines = [f"完成 {d.get('done')} 题，失败 {d.get('failed')} 题。"]
    if d.get("substrate"):
        lines.append(f"substrate: {d.get('substrate')}；rollout 执行 {d.get('execution_count')} 次，"
                     f"编辑器调用 {d.get('editor_calls')} 次。")
    for name in ("tasks", "results", "domains"):
        items = d.get(name)
        if isinstance(items, list) and items:
            lines.append("任务明细：")
            for it in items[:8]:
                if isinstance(it, dict):
                    lines.append(f"  - {it.get('task_id', it.get('id', '?'))}: {it.get('status', it.get('done', '?'))}")
    return {"ok": True, "output": "\n".join(lines)}


def _open_folder(cfg: dict) -> dict:
    folder = ROOT / "runs" / "agns_demo"
    if not folder.exists():
        return {"ok": False, "output": "還没有结果资料夹。請先跑 Demo。"}
    subprocess.Popen(["explorer", str(folder)])
    return {"ok": True, "output": "已用资源管理器打開 runs\\agns_demo"}


_ACTIONS = {
    "run_demo": _run_demo,
    "start_bridge": _start_bridge,
    "test_link": _test_link,
    "show_results": _show_results,
    "open_folder": _open_folder,
}

# ---------------------------------------------------------------- HTML page

HTML = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agnes × Harness² 控制台</title>
<style>
 body{font-family:"Microsoft JhengHei","PingFang TC",sans-serif;background:#f4f6f8;margin:0;padding:24px;color:#0f172a}
 h1{font-size:20px;margin:0 0 4px}
 .sub{color:#64748b;font-size:13px;margin-bottom:16px}
 .card{background:#fff;border-radius:12px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);max-width:780px}
 .card b{font-size:15px}
 small{color:#64748b}
 button{font-size:15px;padding:11px 20px;border:0;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer;margin:8px 8px 8px 0}
 button:hover{background:#1d4ed8}
 button.busy{opacity:.5;pointer-events:none}
 input{font-size:14px;padding:8px;border:1px solid #cbd5e1;border-radius:8px}
 #k{width:60px}
 pre{white-space:pre-wrap;background:#0f172a;color:#d1fae5;padding:12px;border-radius:8px;font-size:13px;min-height:14px;margin:10px 0 0}
 pre.ok{color:#86efac} pre.bad{color:#fca5a5}
 .note{font-size:12px;color:#64748b;margin-top:6px}
</style></head><body>
<h1>Agnes × Harness² 控制台</h1>
<div class="sub">不需要打任何指令。照 ① → ② → ③ 按即可；结果会直接显示在按钮下方。</div>

<div class="card">
 <b>① 跑 Demo（不需要 Agnes API，先用它确認整條线通）</b><br>
 <small>「内建 worker」＝ 无需任何 Agnes 设定即可跑通；「AGNES_CLI」＝ 用你自己的 Agnes 指令來跑（选 ①-B 才用到）。</small>
 <div style="margin-top:10px">
   题数 k：<input id="k" value="1">　
   AGNES_CLI 指令：<input id="cli" placeholder="例：python agnes_bridge\fake_agnes_cli_example.py（或你自己的 agnes 指令）" style="width:62%">
   <div>
     <button onclick="runDemo(false)">①-A 跑 Demo（内建 worker）</button>
     <button onclick="runDemo(true)">①-B 跑 Demo（用 AGNES_CLI）</button>
   </div>
   <pre id="o_demo"></pre>
 </div>
</div>

<div class="card">
 <b>② 接你的 Agnes 模型（Bridge）</b><br>
 <small>Bridge 是把 Harness² 的模型呼叫轉给你 Agnes 端點的轉接器。端點资料（URL / key / model）已经放在 .agns_bridge.env，不用在这填。</small>
 <div style="margin-top:6px">
   <button onclick="call('start_bridge')">②-A 啟動 Bridge</button>
   <button onclick="call('test_link')">②-B 测試 Agnes 連线</button>
 </div>
 <pre id="o_bridge"></pre>
</div>

<div class="card">
 <b>③ 看结果</b>
 <div style="margin-top:6px">
   <button onclick="call('show_results')">③-A 显示最新 Demo 结果</button>
   <button onclick="call('open_folder')">③-B 用资源管理器打開结果资料夹</button>
 </div>
 <pre id="o_results"></pre>
</div>

<script>
const OUT = {run_demo:'o_demo', start_bridge:'o_bridge', test_link:'o_bridge',
             show_results:'o_results', open_folder:'o_results'};
async function call(name, payload){
  const el = document.getElementById(OUT[name]);
  el.className=''; el.textContent='执行中…';
  const btns = document.querySelectorAll('.card button');
  btns.forEach(b=>b.classList.add('busy'));
  try {
    const r = await fetch('/api/'+name, {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload||{})});
    const d = await r.json();
    el.textContent = (d.output||'') + (d.note ? '\n（'+d.note+'）' : '');
    el.className = d.ok ? 'ok' : 'bad';
  } catch(e) { el.textContent = '請求失败：'+e; el.className='bad'; }
  btns.forEach(b=>b.classList.remove('busy'));
}
function runDemo(useCli){
  call('run_demo', {use_cli:useCli,
                    cli:document.getElementById('cli').value,
                    k:document.getElementById('k').value});
}
</script>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
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
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            cfg = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            cfg = {}
        action_name = self.path.lstrip("/").split("/", 1)[-1]
        action = _ACTIONS.get(action_name)
        if action is None:
            self._send(404, json.dumps({"ok": False, "output": "unknown api"}).encode(),
                       "application/json")
            return
        try:
            result = action(cfg)
        except Exception as exc:  # noqa: BLE001 - GUI shows the error, never dies
            result = {"ok": False, "output": f"{type(exc).__name__}: {exc}"}
        self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", GUI_PORT), Handler)
    print("=" * 60)
    print("Agnes x Harness^2 GUI")
    print(f"  open in browser : http://127.0.0.1:{GUI_PORT}")
    print(f"  repo root       : {ROOT}")
    print(f"  bridge will run : http://{os.environ.get('AGNES_PROXY_HOST', '127.0.0.1')}:"
          f"{os.environ.get('AGNES_PROXY_PORT', '8620')}/v1 -> {os.environ.get('AGNES_API_URL', '(unset)')}")
    print("  stop with Ctrl+C")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
