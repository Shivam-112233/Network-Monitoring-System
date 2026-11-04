"""Local web dashboard for the network monitoring system."""

from __future__ import annotations

import platform
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from flask import Flask, redirect, render_template_string, request, url_for

from database import fetch_results, save_result

app = Flask(__name__)
INTERVAL_SECONDS = 60
PING_COUNT = 4
targets: dict[str, str] = {
    "Google DNS": "8.8.8.8",
    "Cloudflare DNS": "1.1.1.1",
    "Google Website": "google.com",
}
latest: dict[str, dict] = {}
lock = threading.RLock()
stop_event = threading.Event()

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="15">
  <title>Network Monitor</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #0b1220; color: #e5edf7; }
    main { max-width: 1100px; margin: 40px auto; padding: 0 22px; }
    h1 { margin-bottom: 6px; } .muted { color: #91a1b8; }
    .card { background: #131e30; border: 1px solid #26364d; border-radius: 12px; padding: 20px; margin: 20px 0; }
    form { display: flex; flex-wrap: wrap; gap: 10px; }
    input { flex: 1 1 190px; min-width: 0; background: #0b1220; border: 1px solid #344760; border-radius: 7px; padding: 11px; color: white; }
    button { border: 0; border-radius: 7px; padding: 10px 14px; background: #3978f6; color: white; cursor: pointer; }
    button.secondary { background: #344760; } button.danger { background: #8d3441; }
    table { width: 100%; border-collapse: collapse; } th, td { padding: 12px 9px; text-align: left; border-bottom: 1px solid #26364d; }
    th { color: #91a1b8; font-weight: 600; } .up { color: #44d19a; font-weight: 700; } .down { color: #ff7584; font-weight: 700; }
    .inline { display: inline; } .inline button { padding: 7px 10px; }
    a { color: #8db5ff; } .actions { white-space: nowrap; }
    @media (max-width: 650px) { table { font-size: 13px; } th, td { padding: 9px 5px; } .hide-small { display: none; } }
  </style>
</head>
<body><main>
  <h1>Network Monitor</h1>
  <div class="muted">ICMP status, average latency, and packet loss · checks every {{ interval }} seconds · page refreshes every 15 seconds</div>
  <section class="card">
    <h2>Add an IP address or hostname</h2>
    <form method="post" action="{{ url_for('add_target') }}">
      <input name="name" placeholder="Device name (e.g. Home Router)" required maxlength="80">
      <input name="host" placeholder="IP address or hostname" required maxlength="253">
      <button type="submit">Add and check</button>
    </form>
  </section>
  <section class="card">
    <h2>Monitored devices</h2>
    <div style="overflow-x:auto"><table><thead><tr><th>Device</th><th>Address</th><th>Status</th><th>Latency</th><th>Packet loss</th><th class="hide-small">Last checked (UTC)</th><th>Actions</th></tr></thead><tbody>
    {% for item in rows %}<tr>
      <td>{{ item.name }}</td><td>{{ item.host }}</td>
      <td class="{{ item.status|lower }}">{{ item.status }}</td>
      <td>{{ item.latency }}</td><td>{{ item.loss }}</td><td class="hide-small">{{ item.checked }}</td>
      <td class="actions"><form class="inline" method="post" action="{{ url_for('check_target', name=item.name) }}"><button class="secondary">Check now</button></form>
      <form class="inline" method="post" action="{{ url_for('remove_target', name=item.name) }}"><button class="danger">Remove</button></form></td>
    </tr>{% else %}<tr><td colspan="7">No targets yet. Add an IP or hostname above.</td></tr>{% endfor %}
    </tbody></table></div>
  </section>
  <section class="card"><h2>Recent saved history</h2>
    <div style="overflow-x:auto"><table><thead><tr><th>Checked (UTC)</th><th>Device</th><th>Address</th><th>Status</th><th>Latency</th><th>Packet loss</th></tr></thead><tbody>
    {% for item in history %}<tr><td>{{ item.checked_at }}</td><td>{{ item.device_name }}</td><td>{{ item.host }}</td><td class="{{ item.status|lower }}">{{ item.status }}</td><td>{{ '%.2f ms'|format(item.average_latency_ms) if item.average_latency_ms is not none else 'N/A' }}</td><td>{{ '%.1f%%'|format(item.packet_loss_percent) }}</td></tr>
    {% else %}<tr><td colspan="6">No saved results yet.</td></tr>{% endfor %}
    </tbody></table></div>
    <p><a href="{{ url_for('history') }}">View full history</a></p>
  </section>
  <p class="muted">A DOWN result means ICMP ping got no reply. Some networks block ping even when a service is online.</p>
</main></body></html>
"""

HISTORY_PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monitoring History</title>
<style>body{font:15px Segoe UI,Arial;background:#0b1220;color:#e5edf7;margin:35px}a{color:#8db5ff}table{border-collapse:collapse;width:100%;margin-top:20px}td,th{text-align:left;border-bottom:1px solid #344760;padding:10px}.up{color:#44d19a}.down{color:#ff7584}</style></head>
<body><h1>Monitoring history</h1><p><a href="{{ url_for('dashboard') }}">← Dashboard</a></p><table><thead><tr><th>Checked (UTC)</th><th>Device</th><th>Address</th><th>Status</th><th>Latency</th><th>Packet loss</th></tr></thead><tbody>
{% for item in history %}<tr><td>{{ item.checked_at }}</td><td>{{ item.device_name }}</td><td>{{ item.host }}</td><td class="{{ item.status|lower }}">{{ item.status }}</td><td>{{ '%.2f ms'|format(item.average_latency_ms) if item.average_latency_ms is not none else 'N/A' }}</td><td>{{ '%.1f%%'|format(item.packet_loss_percent) }}</td></tr>{% else %}<tr><td colspan="6">No saved results.</td></tr>{% endfor %}
</tbody></table></body></html>
"""


def ping_device(host: str) -> dict[str, float | str | None]:
    windows = platform.system().lower() == "windows"
    command = ["ping", "-n" if windows else "-c", str(PING_COUNT), host]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if windows else 0)
        output = f"{completed.stdout}\n{completed.stderr}"
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "DOWN", "average_latency_ms": None, "packet_loss_percent": 100.0}
    loss = re.search(r"\((\d+(?:\.\d+)?)%\s*loss\)", output, re.I) or re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", output, re.I)
    packet_loss = float(loss.group(1)) if loss else (0.0 if completed.returncode == 0 else 100.0)
    latency = re.search(r"Average\s*=\s*(\d+(?:\.\d+)?)\s*ms", output, re.I)
    latency = latency or re.search(r"(?:rtt|round-trip)[^=]*=\s*[\d.]+/([\d.]+)/", output, re.I)
    latency = latency or re.search(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", output, re.I)
    return {"status": "UP" if completed.returncode == 0 and packet_loss < 100 else "DOWN",
            "average_latency_ms": float(latency.group(1)) if latency else None,
            "packet_loss_percent": packet_loss}


def check_one(name: str, host: str) -> dict:
    result = ping_device(host)
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result.update({"host": host, "checked_at": checked})
    save_result(name, host, result)
    with lock:
        latest[name] = result
    if result["status"] == "DOWN":
        print(f"ALERT: DOWN - {name} ({host}) is unreachable.")
    return result


def check_all() -> None:
    with lock:
        snapshot = list(targets.items())
    with ThreadPoolExecutor(max_workers=max(1, len(snapshot))) as pool:
        pending = {pool.submit(check_one, name, host): name for name, host in snapshot}
        for future in as_completed(pending):
            try:
                future.result()
            except Exception as error:
                print(f"Monitoring error for {pending[future]}: {error}")


def monitoring_loop() -> None:
    while not stop_event.is_set():
        check_all()
        stop_event.wait(INTERVAL_SECONDS)


@app.get("/")
def dashboard():
    with lock:
        current_targets = list(targets.items())
        current_results = dict(latest)
    rows = []
    for name, host in current_targets:
        result = current_results.get(name)
        latency = result.get("average_latency_ms") if result else None
        rows.append({"name": name, "host": host, "status": result["status"] if result else "CHECKING",
                     "latency": f"{latency:g} ms" if latency is not None else "N/A",
                     "loss": f"{result['packet_loss_percent']:g}%" if result else "N/A",
                     "checked": result["checked_at"] if result else "Waiting for first check"})
    return render_template_string(PAGE, rows=rows, history=fetch_results(20), interval=INTERVAL_SECONDS)


@app.post("/targets")
def add_target():
    name = request.form.get("name", "").strip()
    host = request.form.get("host", "").strip()
    if name and host:
        with lock:
            targets[name] = host
        check_one(name, host)
    return redirect(url_for("dashboard"))


@app.post("/targets/<name>/check")
def check_target(name: str):
    with lock:
        host = targets.get(name)
    if host:
        check_one(name, host)
    return redirect(url_for("dashboard"))


@app.post("/targets/<name>/remove")
def remove_target(name: str):
    with lock:
        targets.pop(name, None)
        latest.pop(name, None)
    return redirect(url_for("dashboard"))


@app.get("/history")
def history():
    return render_template_string(HISTORY_PAGE, history=fetch_results(500))


if __name__ == "__main__":
    threading.Thread(target=monitoring_loop, name="network-monitor", daemon=True).start()
    print("Dashboard available at http://127.0.0.1:5000 (Ctrl+C to stop).")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
