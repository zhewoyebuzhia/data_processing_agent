#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

PROJECT_ROOT = Path.cwd()
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned" / "wearos_1"
OUTPUT_DIR = PROJECT_ROOT / "data" / "aggregated" / "wearos_1"
TOOLS_DIR = PROJECT_ROOT / "tools" / "wearos_1"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

print(f"Scanning: {CLEANED_DIR}")
files = sorted(CLEANED_DIR.glob("*.jsonl"))
print(f"Found {len(files)} JSONL files")

all_records = []
file_record_map = {}
for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "time" not in record:
                continue
            all_records.append(record)
            file_record_map[len(all_records) - 1] = file.name

print(f"Loaded {len(all_records)} records total")
if len(all_records) == 0:
    print("No records loaded. Exiting.")
    exit(0)

def parse_time(ts):
    if isinstance(ts, datetime):
        return ts
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"]:
        try:
            return datetime.strptime(ts, fmt)
        except (ValueError, TypeError):
            continue
    raise ValueError(f"Cannot parse time: {ts}")

all_records.sort(key=lambda r: parse_time(r["time"]))
print(f"Time range: {all_records[0]['time']} ~ {all_records[-1]['time']}")

WINDOW_SIZE = 20
STEP = 10
windows = []
i = 0
while i + WINDOW_SIZE <= len(all_records):
    window_records = all_records[i:i + WINDOW_SIZE]
    times = [parse_time(r["time"]) for r in window_records]
    start_time = times[0]
    end_time = times[-1]
    date_key = start_time.strftime("%Y-%m-%d")
    gaps = []
    for j in range(1, len(times)):
        gaps.append((times[j] - times[j-1]).total_seconds())
    if gaps:
        min_gap = min(gaps)
        max_gap = max(gaps)
        avg_gap = sum(gaps) / len(gaps)
        interruptions = [g for g in gaps if g > 30]
        interruption_count = len(interruptions)
        interruption_positions = [j for j, g in enumerate(gaps) if g > 30]
    else:
        min_gap = max_gap = avg_gap = 0
        interruption_count = 0
        interruption_positions = []
    actual_span_seconds = (end_time - start_time).total_seconds()
    charging_count = sum(1 for r in window_records if r.get("heart_rate") is None)
    charging_ratio = charging_count / WINDOW_SIZE
    source_files = list(OrderedDict.fromkeys(
        file_record_map[idx] for idx in range(i, i + WINDOW_SIZE) if idx in file_record_map
    ))
    window_meta = {
        "window_id": f"W{len(windows):06d}",
        "date": date_key,
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "record_count": WINDOW_SIZE,
        "actual_span_seconds": round(actual_span_seconds, 2),
        "gap_stats": {
            "min_gap_seconds": round(min_gap, 2),
            "max_gap_seconds": round(max_gap, 2),
            "avg_gap_seconds": round(avg_gap, 2),
            "interruption_count": interruption_count,
            "interruption_positions": interruption_positions
        },
        "charging_ratio": round(charging_ratio, 4),
        "source_files": source_files,
        "records": window_records
    }
    windows.append(window_meta)
    i += STEP

print(f"Generated {len(windows)} windows")

date_windows = {}
for w in windows:
    date_windows.setdefault(w["date"], []).append(w)

print(f"Writing to {len(date_windows)} date files...")
for date_key, win_list in date_windows.items():
    output_file = OUTPUT_DIR / f"aggregated_{date_key}.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for win in win_list:
            f.write(json.dumps(win, ensure_ascii=False) + '\n')
    print(f"  {output_file.name}: {len(win_list)} windows")

tool_path = TOOLS_DIR / "aggregate_windows.py"
with open(tool_path, 'w', encoding='utf-8') as f:
    f.write('#!/usr/bin/env python3\n')
    f.write('"""\n')
    f.write('Aggregate cleaned WearOS sensor data into fixed-size windows (20 records, 50% overlap).\n')
    f.write('Cross-file aggregation is supported to ensure continuity around midnight.\n')
    f.write('Output: JSONL files per date in data/aggregated/wearos_1/\n')
    f.write('"""\n\n')
    f.write('import json\n')
    f.write('from pathlib import Path\n')
    f.write('from datetime import datetime\n')
    f.write('from collections import OrderedDict\n\n')
    f.write('WINDOW_SIZE = 20\n')
    f.write('STEP = 10\n\n')
    f.write('def parse_time(ts):\n')
    f.write('    if isinstance(ts, datetime):\n')
    f.write('        return ts\n')
    f.write('    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"]:\n')
    f.write('        try:\n')
    f.write('            return datetime.strptime(ts, fmt)\n')
    f.write('        except (ValueError, TypeError):\n')
    f.write('            continue\n')
    f.write('    raise ValueError(f"Cannot parse time: {ts}")\n\n')
    f.write('def load_all_records(cleaned_dir):\n')
    f.write('    files = sorted(Path(cleaned_dir).glob("*.jsonl"))\n')
    f.write('    all_records = []\n')
    f.write('    file_record_map = {}\n')
    f.write('    for file in files:\n')
    f.write('        with open(file, "r", encoding="utf-8") as f:\n')
    f.write('            for line in f:\n')
    f.write('                line = line.strip()\n')
    f.write('                if not line:\n')
    f.write('                    continue\n')
    f.write('                try:\n')
    f.write('                    record = json.loads(line)\n')
    f.write('                except json.JSONDecodeError:\n')
    f.write('                    continue\n')
    f.write('                if "time" not in record:\n')
    f.write('                    continue\n')
    f.write('                all_records.append(record)\n')
    f.write('                file_record_map[len(all_records) - 1] = file.name\n')
    f.write('    all_records.sort(key=lambda r: parse_time(r["time"]))\n')
    f.write('    return all_records, file_record_map\n\n')
    f.write('def build_windows(all_records, file_record_map, window_size=WINDOW_SIZE, step=STEP):\n')
    f.write('    windows = []\n')
    f.write('    i = 0\n')
    f.write('    while i + window_size <= len(all_records):\n')
    f.write('        window_records = all_records[i:i + window_size]\n')
    f.write('        times = [parse_time(r["time"]) for r in window_records]\n')
    f.write('        start_time = times[0]\n')
    f.write('        end_time = times[-1]\n')
    f.write('        date_key = start_time.strftime("%Y-%m-%d")\n')
    f.write('        gaps = []\n')
    f.write('        for j in range(1, len(times)):\n')
    f.write