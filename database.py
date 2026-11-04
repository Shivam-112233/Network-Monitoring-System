"""SQLite persistence for network monitoring results."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).with_name("network_monitor.db")


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Open the database and ensure its schema exists."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS monitoring_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT NOT NULL,
            device_name TEXT NOT NULL,
            host TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('UP', 'DOWN')),
            average_latency_ms REAL,
            packet_loss_percent REAL NOT NULL
        )"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_checked_at ON monitoring_results(checked_at)"
    )
    connection.commit()
    return connection


def save_result(device_name: str, host: str, result: dict[str, Any], db_path: str | Path = DB_PATH) -> None:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO monitoring_results
               (checked_at, device_name, host, status, average_latency_ms, packet_loss_percent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (checked_at, device_name, host, result["status"], result["average_latency_ms"], result["packet_loss_percent"]),
        )


def fetch_results(limit: int = 100, db_path: str | Path = DB_PATH) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return connection.execute(
            "SELECT * FROM monitoring_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
