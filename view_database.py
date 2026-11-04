"""Display saved monitoring history from SQLite."""

import argparse

from database import fetch_results


def main() -> None:
    parser = argparse.ArgumentParser(description="View saved network monitoring records.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum records to show (default: 100).")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be greater than zero")
    rows = fetch_results(args.limit)
    if not rows:
        print("No monitoring records found. Run main.py first.")
        return
    print(f"{'Checked (UTC)':25} {'Device':20} {'Host':20} {'Status':6} {'Latency':12} Packet loss")
    print("-" * 105)
    for row in rows:
        latency = f"{row['average_latency_ms']:.2f} ms" if row["average_latency_ms"] is not None else "N/A"
        print(f"{row['checked_at']:25} {row['device_name'][:20]:20} {row['host'][:20]:20} "
              f"{row['status']:6} {latency:12} {row['packet_loss_percent']:.1f}%")


if __name__ == "__main__":
    main()
