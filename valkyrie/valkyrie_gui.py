#!/usr/bin/env python3
"""
Valkyrie GUI — local web dashboard for the Valkyrie scanner.

Launches a small HTTP server bound to 127.0.0.1 and serves a single-page
control panel: configure a scan, start/stop it, watch live progress, browse
findings filtered by severity, and inspect the concrete proof (request +
response excerpt) attached to every confirmed finding.

Run:  python3 valkyrie_gui.py          # then open http://127.0.0.1:8787
The dashboard itself never binds to a public interface.
"""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from valkyrie import Scanner, Client, host_is_local


# ── scan session state ──────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.lock = threading.Lock()
        self.scanner: Scanner | None = None
        self.thread: threading.Thread | None = None
        self.stop_flag = False
        self.started = 0.0
        self.finished = 0.0
        self.error = ""
        self.target = ""

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def stop(self):
        self.stop_flag = True

    def start(self, cfg):
        if self.running():
            return False, "A scan is already running."
        target = cfg.get("target", "").strip()
        if "://" not in target:
            target = "http://" + target
        host = urlparse(target).hostname
        if not host:
            return False, "Could not parse a hostname from the target."
        if not host_is_local(host) and not cfg.get("authorized"):
            return False, ("Target is not loopback/private. Tick "
                           "'I am authorized' only if you have explicit permission.")
        self.stop_flag = False
        self.error = ""
        self.target = target
        client = Client(
            delay=float(cfg.get("delay", 0.15)),
            timeout=float(cfg.get("timeout", 12.0)),
            max_requests=int(cfg.get("max_requests", 2000)),
            verify_tls=not cfg.get("insecure", False),
            cookie=cfg.get("cookie") or None,
            stop_check=lambda: self.stop_flag,
        )
        self.scanner = Scanner(
            target, client,
            max_pages=int(cfg.get("max_pages", 80)),
            fuzz=cfg.get("fuzz", True),
            active=cfg.get("active", True),
            test_forms=cfg.get("forms", True),
            idor=cfg.get("idor", True),
            allow_destructive=cfg.get("allow_destructive", False),
        )
        self.started = time.time()
        self.finished = 0.0

        def _run():
            try:
                self.scanner.run()
            except Exception as e:  # noqa: BLE001
                self.error = repr(e)
            finally:
                self.finished = time.time()

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        return True, "started"

    def state(self):
        sc = self.scanner
        if not sc:
            return {"status": "idle", "findings": []}
        prog = sc.progress()
        findings = [
            {"id": f.id, "severity": f.severity, "title": f.title,
             "url": f.url, "category": f.category, "confirmed": f.confirmed}
            for f in sc.findings
        ]
        return {
            "status": ("running" if self.running() else
                       ("error" if self.error else "done")),
            "target": self.target,
            "phase": prog["phase"],
            "requests": prog["requests"],
            "budget": prog["budget"],
            "pages": prog["pages"],
            "elapsed": round((self.finished or time.time()) - self.started, 1),
            "error": self.error,
            "findings": findings,
        }

    def finding(self, fid):
        if not self.scanner:
            return None
        for f in self.scanner.findings:
            if f.id == fid:
                return asdict(f)
        return None

    def export(self):
        if not self.scanner:
            return {"target": self.target, "findings": []}
        return {
            "target": self.target,
            "requests": self.scanner.client.count,
            "pages": len(self.scanner.visited),
            "findings": [asdict(f) for f in self.scanner.findings],
        }


SESSION = Session()


# ── HTTP handler ────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "ValkyrieGUI"

    def log_message(self, *_):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, INDEX_HTML, "text/html")
        if u.path == "/api/state":
            return self._send(200, SESSION.state())
        if u.path == "/api/finding":
            qs = parse_qs(u.query)
            fid = int(qs.get("id", ["0"])[0])
            f = SESSION.finding(fid)
            return self._send(200 if f else 404, f or {"error": "not found"})
        if u.path == "/api/export":
            self.send_response(200)
            data = json.dumps(SESSION.export(), ensure_ascii=False, indent=2).encode()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition",
                             "attachment; filename=valkyrie-report.json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        if u.path == "/api/scan":
            ok, msg = SESSION.start(payload)
            return self._send(200 if ok else 400, {"ok": ok, "message": msg})
        if u.path == "/api/stop":
            SESSION.stop()
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})


# ── frontend (single page) ──────────────────────────────────────────────────

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Valkyrie — Web Security Scanner</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --border:#2a3340;
    --text:#e6edf3; --muted:#8b949e; --accent:#7c5cff;
    --crit:#ff4d9d; --high:#ff6b6b; --med:#ffb454; --low:#4ec9ff; --info:#8b949e;
  }
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--text)}
  header{display:flex;align-items:center;gap:12px;padding:14px 20px;
         border-bottom:1px solid var(--border);background:var(--panel)}
  header .logo{font-weight:700;font-size:18px;letter-spacing:.5px}
  header .logo span{color:var(--accent)}
  header .tag{color:var(--muted);font-size:12px}
  .wrap{display:grid;grid-template-columns:320px 1fr;gap:0;height:calc(100vh - 53px)}
  .side{border-right:1px solid var(--border);background:var(--panel);
        padding:16px;overflow:auto}
  .main{display:flex;flex-direction:column;overflow:hidden}
  .field{margin-bottom:12px}
  label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}
  input[type=text],input[type=number]{width:100%;padding:8px;border-radius:6px;
        border:1px solid var(--border);background:var(--panel2);color:var(--text)}
  .row{display:flex;gap:8px}
  .row>div{flex:1}
  .check{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px}
  .check input{accent-color:var(--accent)}
  button{cursor:pointer;border:none;border-radius:6px;padding:10px 14px;
         font-weight:600;font-size:13px}
  .btn-go{background:var(--accent);color:#fff;width:100%}
  .btn-stop{background:#30363d;color:var(--text);width:100%;margin-top:8px}
  .btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
  .statusbar{padding:12px 20px;border-bottom:1px solid var(--border);
             background:var(--panel);display:flex;align-items:center;gap:18px;
             flex-wrap:wrap}
  .pill{font-size:12px;color:var(--muted)}
  .pill b{color:var(--text)}
  .bar{flex:1;min-width:120px;height:8px;background:var(--panel2);border-radius:4px;
       overflow:hidden}
  .bar>i{display:block;height:100%;width:0;background:var(--accent);
         transition:width .4s}
  .chips{display:flex;gap:8px;padding:10px 20px;flex-wrap:wrap;
         border-bottom:1px solid var(--border)}
  .chip{padding:4px 10px;border-radius:20px;font-size:12px;cursor:pointer;
        border:1px solid var(--border);background:var(--panel2);user-select:none}
  .chip.active{outline:2px solid var(--accent)}
  .chip b{margin-left:6px}
  .c-critical{color:var(--crit)} .c-high{color:var(--high)}
  .c-medium{color:var(--med)} .c-low{color:var(--low)} .c-info{color:var(--info)}
  .content{flex:1;display:grid;grid-template-columns:1fr 0;overflow:hidden;
           transition:grid-template-columns .2s}
  .content.open{grid-template-columns:1fr 480px}
  .list{overflow:auto}
  table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--border);
        font-size:13px;vertical-align:top}
  th{position:sticky;top:0;background:var(--panel);color:var(--muted);
     font-size:11px;text-transform:uppercase;letter-spacing:.5px}
  tr.frow{cursor:pointer}
  tr.frow:hover{background:var(--panel2)}
  .sev{font-weight:700;text-transform:uppercase;font-size:11px}
  .badge{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:700}
  .b-conf{background:rgba(63,185,80,.15);color:#3fb950}
  .b-pot{background:rgba(255,180,84,.15);color:var(--med)}
  .drawer{border-left:1px solid var(--border);background:var(--panel);
          overflow:auto;padding:18px}
  .drawer h3{margin:0 0 4px}
  .drawer .url{color:var(--low);word-break:break-all;font-size:12px}
  .kv{margin:14px 0}
  .kv .k{font-size:11px;color:var(--muted);text-transform:uppercase;
         letter-spacing:.5px;margin-bottom:4px}
  pre{background:var(--bg);border:1px solid var(--border);border-radius:6px;
      padding:10px;overflow:auto;font-size:12px;white-space:pre-wrap;
      word-break:break-word;max-height:260px}
  .close{float:right;cursor:pointer;color:var(--muted)}
  .empty{padding:40px;text-align:center;color:var(--muted)}
  .note{font-size:11px;color:var(--muted);margin-top:14px;line-height:1.5;
        border-top:1px solid var(--border);padding-top:12px}
</style></head>
<body>
<header>
  <div class="logo">VALK<span>YRIE</span></div>
  <div class="tag">universal web scanner · authorized testing only</div>
</header>
<div class="wrap">
  <aside class="side">
    <div class="field">
      <label>Target URL</label>
      <input id="target" type="text" placeholder="http://localhost:5000" value="http://localhost:5000">
    </div>
    <div class="row">
      <div class="field"><label>Max pages</label>
        <input id="max_pages" type="number" value="80"></div>
      <div class="field"><label>Max requests</label>
        <input id="max_requests" type="number" value="2000"></div>
    </div>
    <div class="row">
      <div class="field"><label>Delay (s)</label>
        <input id="delay" type="number" step="0.05" value="0.15"></div>
      <div class="field"><label>Timeout (s)</label>
        <input id="timeout" type="number" value="12"></div>
    </div>
    <div class="field">
      <label>Cookie (for authenticated scan)</label>
      <input id="cookie" type="text" placeholder="session=...">
    </div>
    <div class="check"><input type="checkbox" id="fuzz" checked>
      <span>Behavioral fuzzing (mutations + anomaly deltas)</span></div>
    <div class="check"><input type="checkbox" id="active" checked>
      <span>Active confirmation (SSTI / SQLi / LFI / cmdi / redirect)</span></div>
    <div class="check"><input type="checkbox" id="forms" checked>
      <span>Form testing (POST/GET, CSRF passthrough)</span></div>
    <div class="check"><input type="checkbox" id="idor" checked>
      <span>IDOR / object enumeration (numeric ids)</span></div>
    <div class="check"><input type="checkbox" id="allow_destructive">
      <span>Submit state-changing forms (disposable data only)</span></div>
    <div class="check"><input type="checkbox" id="insecure">
      <span>Skip TLS verification</span></div>
    <div class="check"><input type="checkbox" id="authorized">
      <span>I am authorized to test a non-local target</span></div>
    <button class="btn-go" id="go">▶ Start scan</button>
    <button class="btn-stop" id="stop">■ Stop</button>
    <button class="btn-ghost" id="export" style="width:100%;margin-top:8px">⬇ Export JSON</button>
    <div class="note">
      Scans only systems you own or are authorized to test. Active checks send
      real payloads (e.g. <code>sleep</code>, <code>{{7*8}}</code>,
      <code>../etc/passwd</code>) to confirm exploitability — run them against
      your own server. No detection-evasion or brute-forcing is performed.
    </div>
  </aside>

  <section class="main">
    <div class="statusbar">
      <div class="pill">status <b id="st">idle</b></div>
      <div class="pill">phase <b id="ph">—</b></div>
      <div class="bar"><i id="prog"></i></div>
      <div class="pill"><b id="reqs">0</b>/<span id="budget">0</span> reqs</div>
      <div class="pill"><b id="pages">0</b> pages</div>
      <div class="pill"><b id="elapsed">0</b>s</div>
    </div>
    <div class="chips" id="chips"></div>
    <div class="content" id="content">
      <div class="list">
        <table>
          <thead><tr><th>Sev</th><th>Status</th><th>Finding</th><th>Category</th></tr></thead>
          <tbody id="rows"></tbody>
        </table>
        <div class="empty" id="empty">No findings yet. Configure a target and start a scan.</div>
      </div>
      <div class="drawer" id="drawer"></div>
    </div>
  </section>
</div>
<script>
const $=s=>document.querySelector(s);
let filter=null, lastCount=-1, detailId=null;
const SEV=["critical","high","medium","low","info"];

function cfg(){return{
  target:$("#target").value, max_pages:+$("#max_pages").value,
  max_requests:+$("#max_requests").value, delay:+$("#delay").value,
  timeout:+$("#timeout").value, cookie:$("#cookie").value,
  fuzz:$("#fuzz").checked, active:$("#active").checked,
  forms:$("#forms").checked, idor:$("#idor").checked,
  allow_destructive:$("#allow_destructive").checked,
  insecure:$("#insecure").checked, authorized:$("#authorized").checked};}

async function start(){
  const r=await fetch("/api/scan",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(cfg())});
  const j=await r.json();
  if(!j.ok){alert(j.message);} lastCount=-1;
}
async function stop(){await fetch("/api/stop",{method:"POST"});}

$("#go").onclick=start;
$("#stop").onclick=stop;
$("#export").onclick=()=>location.href="/api/export";

function chip(sev,n){
  const active=filter===sev?"active":"";
  return `<div class="chip ${active}" data-sev="${sev}">
    <span class="c-${sev}">${sev}</span><b>${n}</b></div>`;
}

function render(state){
  $("#st").textContent=state.status||"idle";
  $("#ph").textContent=state.phase||"—";
  $("#reqs").textContent=state.requests||0;
  $("#budget").textContent=state.budget||0;
  $("#pages").textContent=state.pages||0;
  $("#elapsed").textContent=state.elapsed||0;
  const pct=state.budget?Math.min(100,100*state.requests/state.budget):0;
  $("#prog").style.width=(state.status==="running"?pct:(state.status==="done"?100:pct))+"%";

  const f=state.findings||[];
  const counts={}; SEV.forEach(s=>counts[s]=0);
  f.forEach(x=>counts[x.severity]=(counts[x.severity]||0)+1);
  $("#chips").innerHTML=`<div class="chip ${filter===null?'active':''}" data-sev="all">all<b>${f.length}</b></div>`
     +SEV.map(s=>chip(s,counts[s])).join("");
  document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{
    const s=c.dataset.sev; filter=(s==="all")?null:s; lastCount=-1; pull();});

  const shown=f.filter(x=>!filter||x.severity===filter)
    .sort((a,b)=>SEV.indexOf(a.severity)-SEV.indexOf(b.severity)
       || (b.confirmed-a.confirmed));
  $("#empty").style.display=shown.length?"none":"block";
  $("#rows").innerHTML=shown.map(x=>`
    <tr class="frow" data-id="${x.id}">
      <td class="sev c-${x.severity}">${x.severity}</td>
      <td><span class="badge ${x.confirmed?'b-conf':'b-pot'}">${x.confirmed?'confirmed':'potential'}</span></td>
      <td>${esc(x.title)}<div class="url">${esc(x.url)}</div></td>
      <td>${esc(x.category||'')}</td>
    </tr>`).join("");
  document.querySelectorAll(".frow").forEach(r=>r.onclick=()=>openDetail(+r.dataset.id));
}

function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

async function openDetail(id){
  detailId=id;
  const r=await fetch("/api/finding?id="+id); const f=await r.json();
  if(f.error){return;}
  const p=f.proof||{};
  const reqHdrs=Object.entries(p.request_headers||{}).map(([k,v])=>`${k}: ${v}`).join("\n");
  const resHdrs=Object.entries(p.response_headers||{}).map(([k,v])=>`${k}: ${v}`).join("\n");
  $("#content").classList.add("open");
  $("#drawer").innerHTML=`
    <span class="close" id="cl">✕ close</span>
    <h3 class="c-${f.severity}">${esc(f.title)}</h3>
    <span class="badge ${f.confirmed?'b-conf':'b-pot'}">${f.confirmed?'confirmed':'potential'}</span>
    <div class="kv"><div class="k">Endpoint</div><div class="url">${esc(f.url)}</div></div>
    <div class="kv"><div class="k">Detail</div><div>${esc(f.detail)}</div></div>
    <div class="kv"><div class="k">How it was verified</div><div>${esc(f.confirmation||'—')}</div></div>
    <div class="kv"><div class="k">Evidence</div><pre>${esc(f.evidence||'—')}</pre></div>
    <div class="kv"><div class="k">Proof · request</div>
      <pre>${esc((p.method||'GET')+' '+(p.url||''))}\n${esc(reqHdrs)}</pre></div>
    <div class="kv"><div class="k">Proof · response (${p.status||0}, ${p.elapsed_ms||0}ms)</div>
      <pre>${esc(resHdrs)}\n\n${esc(p.response_excerpt||'')}</pre></div>`;
  $("#cl").onclick=()=>{$("#content").classList.remove("open");detailId=null;};
}

async function pull(){
  try{
    const r=await fetch("/api/state"); const s=await r.json();
    render(s);
  }catch(e){}
}
setInterval(pull,1200); pull();
</script>
</body></html>
"""


def main():
    host, port = "127.0.0.1", 8787
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"\n  Valkyrie GUI → {url}")
    print("  (dashboard bound to loopback only; Ctrl+C to quit)\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
