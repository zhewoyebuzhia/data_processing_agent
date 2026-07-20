#!/usr/bin/env python3
"""Collect laptop battery level and current time every 30 seconds."""

import json
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


def collect_battery() -> dict:
    """Collect current timestamp and battery level.

    Returns:
        dict with 'timestamp' (ISO 8601) and 'battery_level' (int 0-100 or None).

    Raises:
        RuntimeError: if battery info cannot be obtained.
    """
    if psutil is None:
        raise RuntimeError("psutil is not installed. Install it with: pip install psutil")

    battery = psutil.sensors_battery()
    if battery is None:
        raise RuntimeError("No battery sensor found on this device")

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    battery_level = int(battery.percent) if battery.percent is not None else None

    return {
        "timestamp": timestamp,
        "battery_level": battery_level,
    }


def main():
    """Run collection once and append result to JSONL file."""
    output_path = Path("data/raw/laptop_1/collection.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        record = collect_battery()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Record written to {output_path}: {record}")


if __name__ == "__main__":
    main()