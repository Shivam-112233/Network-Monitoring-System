# Advanced Network Monitoring and Alert System

A dependency-free Python 3 command-line monitor that checks multiple hosts with ICMP ping, reports reachability, average latency and packet loss, prints a clear alert for unreachable hosts, and saves every result to SQLite.

## Requirements

- Python 3.9 or later
- The system `ping` utility available on `PATH`
- Network permissions that allow ICMP traffic (some networks/firewalls block ping)

No third-party Python packages are required. The SQLite database is created automatically beside the scripts the first time monitoring or history viewing runs.

## Run

```bash
python main.py
```

Monitoring repeats every 60 seconds by default. Stop it with `Ctrl+C`. To change the interval or run only one cycle:

```bash
python main.py --interval 30
python main.py --once
```

To check any one IP address or hostname without editing the source, pass `--host`. Add `--name` to choose the display name:

```bash
python main.py --host 192.168.1.1 --name "Home Router"
python main.py --host example.com --once
```

The initial targets are Google DNS (`8.8.8.8`), Cloudflare DNS (`1.1.1.1`), and `google.com`. Add targets to the `DEVICES` dictionary in `main.py` using a descriptive name as the key and hostname/IP as its value.

## View history

```bash
python view_database.py
python view_database.py --limit 25
```

## Web dashboard

Install the dashboard dependency once, then start the web app:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in a browser. The dashboard shows live status and recent saved history, checks targets every 60 seconds, and lets you add, check, and remove an IP/hostname. Targets added through the page remain in memory until the app is stopped; their monitoring records are saved permanently in SQLite. Stop the dashboard with `Ctrl+C` in the terminal.

Timestamps are stored in UTC. The history view lists newest records first. The database file is `network_monitor.db`.

## Notes

The program runs one ping process per target concurrently. On Windows it uses `ping -n 4`; on Linux/macOS it uses `ping -c 4`. A host is marked DOWN when all probes fail, ping cannot be run, or the process times out. Partial packet loss is reported while the host remains UP if at least one probe succeeds. ICMP is not always enabled for websites or cloud services, so a DOWN result means ping did not get a response, not necessarily that an HTTP service is unavailable.
