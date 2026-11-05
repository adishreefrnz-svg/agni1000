"""Read-only local dashboard for camera observations and sensor telemetry."""

from __future__ import annotations

import argparse
import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "output_recordings" / "detections.csv"
DEFAULT_SCREENSHOTS = ROOT / "screenshots"
DEFAULT_TELEMETRY = ROOT / "output_recordings" / "telemetry.json"

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FireRescueAI | Review dashboard</title>
<style>
:root{color-scheme:dark;--bg:#0b1115;--panel:#131d22;--line:#26383e;--text:#e8f0ed;--muted:#9bb0aa;--accent:#f3a64a;--warn:#ffd28a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}
main{max-width:1180px;margin:auto;padding:28px 20px 56px}header{border-bottom:1px solid var(--line);padding-bottom:18px}
h1{font-size:clamp(1.7rem,4vw,2.4rem);margin:.1rem 0;color:var(--accent)}h2{font-size:1.15rem;margin:0 0 14px}
.notice{border-left:4px solid var(--warn);padding:10px 14px;background:#282116;color:var(--warn);margin:18px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:18px 0 28px}
.card,section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.metric{font-size:1.8rem;font-weight:700;color:var(--accent)}.label,.muted{color:var(--muted);font-size:.9rem}
.sensors{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.sensor{background:#10181c;border:1px solid var(--line);border-radius:9px;padding:14px}.sensor h3{margin:0 0 8px;font-size:1rem}
.status{font-weight:650}.error{color:#ff9b8e;overflow-wrap:anywhere}.ok{color:#a6e3b2}
section{margin-top:16px;overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:680px}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:.84rem}
footer{margin-top:20px;color:var(--muted);font-size:.85rem}code{color:#f3c58b}
</style></head>
<body><main><header><p class="muted">LOCAL RESEARCH REVIEW</p><h1>FireRescueAI dashboard</h1><p class="muted">Camera observations and connected sensor readings. No flight controls.</p></header>
<div class="notice"><strong>Unverified data — human review required.</strong> This prototype does not confirm people, infer safety or emergencies, identify targets, or make rescue decisions. RGB camera detections do not see through smoke or other obscurants.</div>
<div class="grid"><div class="card"><div class="metric" id="detection-count">—</div><div class="label">detection rows</div></div><div class="card"><div class="metric" id="track-count">—</div><div class="label">distinct tracking IDs (not verified people)</div></div><div class="card"><div class="metric" id="screenshot-count">—</div><div class="label">saved screenshots</div></div><div class="card"><div class="metric" id="csv-state">—</div><div class="label">detection log</div></div></div>
<section><h2>Sensor inputs</h2><div class="sensors" id="sensors"><p class="muted">Waiting for telemetry…</p></div><p class="muted">The SEN0395 is shown as raw serial text only; no human-presence or life conclusion is made.</p></section>
<section><h2>Recent camera observations</h2><table><thead><tr><th>UTC time</th><th>Frame</th><th>Track ID</th><th>Confidence</th><th>Bounding box</th></tr></thead><tbody id="detections"><tr><td colspan="5" class="muted">Waiting for detection log…</td></tr></tbody></table></section>
<section><h2>Saved screenshots</h2><ul id="screenshots"><li class="muted">None recorded.</li></ul></section>
<footer>Refreshes automatically every 3 seconds. Latest update: <span id="updated">waiting</span>. The dashboard is read-only.</footer></main>
<script>
const text=(id,value)=>{document.getElementById(id).textContent=value};
function cell(row,value){const td=document.createElement('td');td.textContent=value??'';row.appendChild(td);return td;}
function showSensors(sensors){const root=document.getElementById('sensors');root.replaceChildren();for(const [name,item] of Object.entries(sensors||{})){const card=document.createElement('article');card.className='sensor';const title=document.createElement('h3');title.textContent=name;card.appendChild(title);const status=document.createElement('div');status.className='status '+(item.status==='connected'?'ok':item.status==='error'?'error':'');status.textContent=item.status||'not started';card.appendChild(status);if(item.updated_at){const time=document.createElement('div');time.className='muted';time.textContent='Updated '+item.updated_at;card.appendChild(time);}if(item.error){const error=document.createElement('p');error.className='error';error.textContent=item.error;card.appendChild(error);}for(const [key,value] of Object.entries(item.data||{})){const detail=document.createElement('p');detail.className='muted';detail.textContent=key.replaceAll('_',' ')+': '+(typeof value==='object'?JSON.stringify(value):String(value));card.appendChild(detail);}root.appendChild(card);}}
async function refresh(){try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();const d=data.detections;text('detection-count',d.count);text('track-count',d.track_ids);text('screenshot-count',data.screenshots.length);text('csv-state',d.available?'available':'not created');text('updated',new Date().toLocaleTimeString());showSensors(data.sensors);const body=document.getElementById('detections');body.replaceChildren();if(!d.recent.length){const row=document.createElement('tr');const empty=cell(row,d.available?'No detection rows recorded.':'Run the detector with --csv to create the log.');empty.colSpan=5;empty.className='muted';body.appendChild(row);}else{for(const entry of d.recent){const row=document.createElement('tr');cell(row,entry.timestamp_utc);cell(row,entry.frame);cell(row,entry.track_id||'?');cell(row,entry.confidence);cell(row,`(${entry.x1}, ${entry.y1}) - (${entry.x2}, ${entry.y2})`);body.appendChild(row);}}const list=document.getElementById('screenshots');list.replaceChildren();if(!data.screenshots.length){const li=document.createElement('li');li.className='muted';li.textContent='None recorded.';list.appendChild(li);}else{for(const name of data.screenshots){const li=document.createElement('li');li.textContent=name;list.appendChild(li);}}}catch(error){text('updated','Dashboard read error: '+error.message);}}
refresh();setInterval(refresh,3000);
</script></body></html>"""


def load_status(csv_path: Path, screenshot_dir: Path, telemetry_path: Path) -> dict:
    rows: list[dict[str, str]] = []
    csv_available = csv_path.is_file()
    if csv_available:
        with csv_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
    track_ids = {row.get("track_id", "") for row in rows if row.get("track_id")}
    telemetry = {
        "gps": {"status": "not_started", "data": None},
        "mpu6050": {"status": "not_started", "data": None},
        "radar": {"status": "not_started", "data": None},
    }
    if telemetry_path.is_file():
        with telemetry_path.open(encoding="utf-8") as file:
            saved = json.load(file)
        telemetry.update(saved.get("sensors", {}))
    screenshots = sorted(path.name for path in screenshot_dir.glob("*.jpg")) if screenshot_dir.is_dir() else []
    return {
        "detections": {
            "available": csv_available,
            "count": len(rows),
            "track_ids": len(track_ids),
            "recent": rows[-25:],
        },
        "sensors": telemetry,
        "screenshots": screenshots[-50:],
    }


def serve(csv_path: Path, screenshot_dir: Path, telemetry_path: Path, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/":
                body = HTML.encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif route == "/api/status":
                body = json.dumps(load_status(csv_path, screenshot_dir, telemetry_path)).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif route == "/healthz":
                body = b"ok\n"
                content_type = "text/plain; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    actual_port = server.server_address[1]
    print(f"Read-only review dashboard: http://{host}:{actual_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Dashboard stopped.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--screenshots", type=Path, default=DEFAULT_SCREENSHOTS)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 only on a trusted local network")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.csv, args.screenshots, args.telemetry, args.host, args.port)


if __name__ == "__main__":
    main()
