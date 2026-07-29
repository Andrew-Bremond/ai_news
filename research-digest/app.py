#!/usr/bin/env python3
"""Local control desk. Private, single-user, binds to localhost only.

    python app.py    ->    http://127.0.0.1:5000
"""
from __future__ import annotations

import threading
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from digest import pipeline
from digest.llm import provider_status

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent

RUN = {"active": False, "log": [], "report": None}
LOCK = threading.Lock()


def _drafts():
    out = ROOT / pipeline.load_config()["paths"]["out"]
    if not out.exists():
        return []
    return sorted((p for p in out.glob("*.md")), key=lambda p: p.name, reverse=True)[:12]


def _worker(profile, provider, skip_llm):
    def log(msg):
        with LOCK:
            RUN["log"].append(str(msg))
    try:
        report = pipeline.run(pipeline.load_config(), profile, provider, skip_llm, log=log)
    except Exception as exc:
        log(f"! run failed — {type(exc).__name__}: {exc}")
        report = {"warnings": [str(exc)]}
    with LOCK:
        RUN["report"] = report
        RUN["active"] = False


@app.get("/")
def index():
    cfg = pipeline.load_config()
    profiles = [(n, pipeline.load_profile(n)) for n in pipeline.list_profiles()]
    active = cfg["active_profile"]
    return render_template_string(
        PAGE,
        profiles=profiles,
        active=active,
        profile=dict(pipeline.load_profile(active)),
        providers=provider_status(cfg["llm"]["models"]),
        default_provider=cfg["llm"]["provider"],
        drafts=_drafts(),
    )


@app.post("/run")
def start_run():
    with LOCK:
        if RUN["active"]:
            return jsonify({"error": "A run is already in progress."}), 409
        RUN.update(active=True, log=[], report=None)
    data = request.get_json(force=True)
    threading.Thread(
        target=_worker,
        args=(data.get("profile"), data.get("provider"), bool(data.get("skip_llm"))),
        daemon=True,
    ).start()
    return jsonify({"started": True})


@app.get("/status")
def status():
    with LOCK:
        return jsonify({"active": RUN["active"], "log": RUN["log"], "report": RUN["report"]})


@app.get("/draft/<path:name>")
def draft(name):
    p = (ROOT / pipeline.load_config()["paths"]["out"] / name).resolve()
    out_dir = (ROOT / pipeline.load_config()["paths"]["out"]).resolve()
    if out_dir not in p.parents or not p.exists():
        return "Not found", 404
    return f"<pre>{p.read_text()}</pre>", 200, {"Content-Type": "text/html; charset=utf-8"}


PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Desk</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#E4E2DC; --panel:#D9D6CE; --ink:#16181A; --muted:#6B6F73;
    --rule:#B9B5AB; --structure:#22405C; --signal:#B23A18; --ok:#3E6B4F;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
       font:400 14px/1.55 "IBM Plex Mono",ui-monospace,monospace}
  .wrap{max-width:820px;margin:0 auto;padding:40px 22px 80px}

  header{border-bottom:2px solid var(--ink);padding-bottom:10px;margin-bottom:0}
  h1{font:700 30px/1 "Archivo Narrow",sans-serif;letter-spacing:.04em;
     text-transform:uppercase;margin:0}
  .sub{color:var(--muted);font-size:12px;margin-top:6px;letter-spacing:.06em}

  section{border-bottom:1px solid var(--rule);padding:22px 0}
  .eyebrow{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.18em;
           text-transform:uppercase;color:var(--structure);margin-bottom:14px}

  .field{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
  label{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
        min-width:88px}
  select{font:500 14px/1 "IBM Plex Mono",monospace;color:var(--ink);
         background:var(--panel);border:1px solid var(--ink);border-radius:0;
         padding:9px 12px;min-width:280px;flex:1;appearance:none;
         background-image:linear-gradient(45deg,transparent 50%,var(--ink) 50%),
                          linear-gradient(135deg,var(--ink) 50%,transparent 50%);
         background-position:calc(100% - 18px) 17px,calc(100% - 13px) 17px;
         background-size:5px 5px,5px 5px;background-repeat:no-repeat}
  select:focus-visible,button:focus-visible,input:focus-visible{
         outline:2px solid var(--signal);outline-offset:2px}
  select option:disabled{color:var(--muted)}

  .desc{color:var(--muted);font-size:13px;margin:4px 0 12px}
  .stats{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--rule);background:var(--panel)}
  .stat{flex:1;min-width:96px;padding:10px 12px;border-right:1px solid var(--rule)}
  .stat:last-child{border-right:0}
  .stat b{display:block;font:700 20px/1 "Archivo Narrow",sans-serif}
  .stat span{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}

  .lamps{margin:14px 0 4px;font-size:12px}
  .lamp{display:flex;gap:10px;align-items:baseline;padding:3px 0;color:var(--muted)}
  .lamp b{color:var(--ink);font-weight:500;min-width:200px}
  .dot{width:8px;height:8px;border-radius:50%;flex:none;translate:0 -1px}
  .dot.on{background:var(--ok)} .dot.off{background:var(--rule)}

  .row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:18px}
  .check{display:flex;gap:8px;align-items:center;font-size:12px;
         letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
  input[type=checkbox]{accent-color:var(--structure);width:15px;height:15px}

  button{font:700 13px/1 "Archivo Narrow",sans-serif;letter-spacing:.14em;
         text-transform:uppercase;background:var(--signal);color:var(--paper);
         border:0;border-radius:0;padding:14px 26px;cursor:pointer;margin-left:auto}
  button:hover{background:var(--ink)}
  button:disabled{background:var(--rule);color:var(--paper);cursor:not-allowed}

  #log{background:var(--ink);color:#D6D2C8;padding:16px;font-size:12.5px;
       white-space:pre-wrap;max-height:340px;overflow:auto;display:none}
  #log.show{display:block}
  #log .warn{color:#E0985F} #log .done{color:#8FBF9F}

  ul{list-style:none;padding:0;margin:0}
  li{border-bottom:1px dotted var(--rule);padding:9px 0;display:flex;gap:12px}
  li:last-child{border:0}
  a{color:var(--structure);text-decoration:none;border-bottom:1px solid var(--rule)}
  a:hover{border-color:var(--structure)}
  .empty{color:var(--muted);font-size:13px}
  @media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
  @media (max-width:560px){label{min-width:100%}select{min-width:100%}button{width:100%;margin:0}}
</style></head><body>
<div class="wrap">
<header>
  <h1>Research Desk</h1>
  <div class="sub">Private weekly digest · drafts are never published automatically</div>
</header>

<section>
  <div class="eyebrow">Interest profile</div>
  <div class="field">
    <label for="profile">Profile</label>
    <select id="profile">
      {% for name, p in profiles %}
      <option value="{{name}}" {% if name==active %}selected{% endif %}>{{p.name}} — {{name}}.yaml</option>
      {% endfor %}
    </select>
  </div>
  <p class="desc">{{profile.description}}</p>
  <div class="stats">
    <div class="stat"><b>{{profile.sources.rss|length}}</b><span>Feeds</span></div>
    <div class="stat"><b>{{profile.sources.arxiv.categories|length}}</b><span>arXiv cats</span></div>
    <div class="stat"><b>{{profile.scoring.keywords|length}}</b><span>Keywords</span></div>
  </div>
  <p class="desc" style="margin-top:12px">Edit <code>profiles/{{active}}.yaml</code> to change what this desk cares about. Add a new file to add a new subject.</p>
</section>

<section>
  <div class="eyebrow">Ranking engine</div>
  <div class="field">
    <label for="provider">Provider</label>
    <select id="provider">
      {% for p in providers %}
      <option value="{{p.key}}" {% if not p.ready %}disabled{% endif %}
        {% if p.key==default_provider and p.ready %}selected{% endif %}>
        {{p.label}} · {{p.model}}{% if not p.ready %} — {{p.reason}}{% endif %}
      </option>
      {% endfor %}
    </select>
  </div>
  <div class="lamps">
    {% for p in providers %}
    <div class="lamp"><span class="dot {{'on' if p.ready else 'off'}}"></span>
      <b>{{p.label}}</b><span>{{p.reason}}</span></div>
    {% endfor %}
  </div>
  <div class="row">
    <span class="check"><input type="checkbox" id="skip"><label for="skip" style="min-width:0">Heuristics only — no API calls</label></span>
    <button id="go">Run digest</button>
  </div>
</section>

<section>
  <div class="eyebrow">Run log</div>
  <div id="log"></div>
  <p class="empty" id="idle">Nothing running.</p>
</section>

<section style="border:0">
  <div class="eyebrow">Drafts awaiting commentary</div>
  <ul>
    {% for d in drafts %}
    <li><a href="/draft/{{d.name}}">{{d.name}}</a></li>
    {% else %}
    <li class="empty">No drafts yet. Run the pipeline.</li>
    {% endfor %}
  </ul>
</section>
</div>

<script>
const log = document.getElementById('log'), idle = document.getElementById('idle'),
      go = document.getElementById('go');

function write(lines, report){
  log.classList.add('show'); idle.style.display='none';
  let html = lines.map(l => `<div>${l.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</div>`).join('');
  if (report){
    (report.warnings||[]).forEach(w => html += `<div class="warn">warning: ${w}</div>`);
    if (report.output) html += `<div class="done">Draft ready: ${report.output} — fill in the commentary blocks.</div>`;
  }
  log.innerHTML = html; log.scrollTop = log.scrollHeight;
}

async function poll(){
  const r = await (await fetch('/status')).json();
  write(r.log, r.report);
  if (r.active) setTimeout(poll, 900);
  else { go.disabled = false; go.textContent = 'Run digest'; if (r.report && r.report.output) setTimeout(()=>location.reload(), 1500); }
}

go.addEventListener('click', async () => {
  go.disabled = true; go.textContent = 'Running…';
  const body = { profile: document.getElementById('profile').value,
                 provider: document.getElementById('provider').value,
                 skip_llm: document.getElementById('skip').checked };
  const res = await fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!res.ok){ write([(await res.json()).error]); go.disabled=false; go.textContent='Run digest'; return; }
  poll();
});
</script>
</body></html>"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
