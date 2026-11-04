"""Continuous, cross-platform ICMP network monitor."""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import save_result

DEVICES = {
    "Google DNS": "8.8.8.8",
    "Cloudflare DNS": "1.1.1.1",
    "Google Website": "google.com",
}
PING_COUNT = 4


def ping_device(host: str) -> dict[str, float | str]:
    """Ping a host and return status, average latency in ms, and packet loss."""
    windows = platform.system().lower() == "windows"
    command = ["ping", "-n" if windows else "-c", str(PING_COUNT), host]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=15, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if windows else 0,
        )
        output = f"{completed.stdout}\n{completed.stderr}"
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "DOWN", "average_latency_ms": None, "packet_loss_percent": 100.0}

    # Windows: "Lost = 1 (25% loss)"; Unix: "1 packets transmitted, 0 received, 100% packet loss"
    loss_match = re.search(r"\((\d+(?:\.\d+)?)%\s*loss\)", output, re.IGNORECASE)
    if not loss_match:
        loss_match = re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", output, re.IGNORECASE)
    packet_loss = float(loss_match.group(1)) if loss_match else (0.0 if completed.returncode == 0 else 100.0)

    # Windows reports Average = 12ms; Unix commonly reports rtt min/avg/max/mdev = x/y/...
    latency_match = re.search(r"Average\s*=\s*(\d+(?:\.\d+)?)\s*ms", output, re.IGNORECASE)
    if not latency_match:
        latency_match = re.search(r"(?:rtt|round-trip)[^=]*=\s*[\d.]+/([\d.]+)/", output, re.IGNORECASE)
    if not latency_match:
        latency_match = re.search(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", output, re.IGNORECASE)
    latency = float(latency_match.group(1)) if latency_match else None
    status = "UP" if completed.returncode == 0 and packet_loss < 100 else "DOWN"
    return {"status": status, "average_latency_ms": latency, "packet_loss_percent": packet_loss}


def monitor_once(devices: dict[str, str] = DEVICES) -> None:
    with ThreadPoolExecutor(max_workers=max(1, len(devices))) as pool:
        checks = {pool.submit(ping_device, host): (name, host) for name, host in devices.items()}
        for future in as_completed(checks):
            name, host = checks[future]
            try:
                result = future.result()
            except Exception as error:  # Keep one failed check from stopping the monitoring cycle.
                result = {"status": "DOWN", "average_latency_ms": None, "packet_loss_percent": 100.0}
                print(f"Check error for {name}: {error}")
            save_result(name, host, result)
            latency = result["average_latency_ms"]
            latency_text = f"{latency:g} ms" if latency is not None else "N/A"
            print(f"Device: {name}\nAddress: {host}\nStatus: {result['status']}\n"
                  f"Average Latency: {latency_text}\nPacket Loss: {result['packet_loss_percent']:g}%")
            if result["status"] == "DOWN":
                print(f"ALERT: DOWN - {name} ({host}) is unreachable; packet loss {result['packet_loss_percent']:g}%.")
            print("-" * 48)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor network devices using ICMP ping.")
    parser.add_argument("--interval", type=float, default=60, help="Seconds between checks (default: 60).")
    parser.add_argument("--once", action="store_true", help="Run one monitoring cycle and exit.")
    parser.add_argument("--host", help="Monitor one IP address or hostname instead of the built-in targets.")
    parser.add_argument("--name", help="Friendly name for --host (defaults to the host value).")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be greater than zero")
    if args.name and not args.host:
        parser.error("--name can only be used together with --host")
    devices = {args.name or args.host: args.host} if args.host else DEVICES
    print(f"Monitoring {len(devices)} device(s); interval={args.interval:g}s. Press Ctrl+C to stop.")
    try:
        while True:
            started = time.monotonic()
            monitor_once(devices)
            if args.once:
                break
            time.sleep(max(0.0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


if __name__ == "__main__":
    main()
