import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 路径配置 - 使用相对路径
PROJECT_ROOT = Path.cwd()
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "wearos_1"
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned" / "wearos_1"
AGGREGATED_DIR = PROJECT_ROOT / "data" / "aggregated" / "wearos_1"
TOOLS_DIR = PROJECT_ROOT / "tools" / "wearos_1"

# 确保输出目录存在
AGGREGATED_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# 窗口参数
WINDOW_SIZE = 20
STEP_SIZE = 10

def load_all_records(cleaned_dir):
    """加载所有清洗后的JSONL文件，返回按时间排序的记录列表"""
    all_records = []
    files = sorted(cleaned_dir.glob("*.jsonl"))
    print(f"数据目录路径: {cleaned_dir}")
    print(f"目录是否存在: {cleaned_dir.exists()}")
    print(f"找到 {len(files)} 个JSONL文件")
    for f in files:
        print(f"  - {f.name}")
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"{file.name}: {len(lines)} 条记录")
            for line in lines:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    # 检查字段名，兼容不同命名
                    ts = record.get('timestamp') or record.get('time') or record.get('datetime') or record.get('record_time')
                    if ts is None:
                        print(f"⚠️ 跳过无时间字段的记录: {list(record.keys())}")
                        continue
                    record['timestamp'] = ts
                    record['_source_file'] = file.name
                    all_records.append(record)
    # 按时间排序
    all_records.sort(key=lambda x: x['timestamp'])
    print(f"共加载 {len(all_records)} 条记录")
    if len(all_records) == 0:
        print("⚠️ 警告：没有加载到任何数据，请检查文件格式")
    return all_records

def compute_gap_stats(records):
    """计算记录间隔统计信息"""
    if len(records) < 2:
        return {"min_gap": None, "max_gap": None, "avg_gap": None, "gaps_over_30s": 0, "gap_positions": []}
    gaps = []
    gap_positions = []
    for i in range(1, len(records)):
        t1 = datetime.strptime(records[i-1]['timestamp'], '%Y-%m-%d %H:%M:%S')
        t2 = datetime.strptime(records[i]['timestamp'], '%Y-%m-%d %H:%M:%S')
        gap = (t2 - t1).total_seconds()
        gaps.append(gap)
        if gap > 30:
            gap_positions.append({"index": i, "gap_seconds": gap, "between": [records[i-1]['timestamp'], records[i]['timestamp']]})
    if gaps:
        return {
            "min_gap": min(gaps),
            "max_gap": max(gaps),
            "avg_gap": sum(gaps) / len(gaps),
            "gaps_over_30s": len(gap_positions),
            "gap_positions": gap_positions
        }
    else:
        return {"min_gap": None, "max_gap": None, "avg_gap": None, "gaps_over_30s": 0, "gap_positions": []}

def compute_charging_ratio(records):
    """计算充电记录占比（心率字段为null视为充电）"""
    if len(records) == 0:
        return 0.0
    charging_count = sum(1 for r in records if r.get('heart_rate') is None)
    return charging_count / len(records)

def aggregate_windows(records):
    """按滑动窗口聚合记录，返回窗口列表"""
    windows = []
    window_id = 0
    i = 0
    while i + WINDOW_SIZE <= len(records):
        window_records = records[i:i+WINDOW_SIZE]
        first_ts = datetime.strptime(window_records[0]['timestamp'], '%Y-%m-%d %H:%M:%S')
        last_ts = datetime.strptime(window_records[-1]['timestamp'], '%Y-%m-%d %H:%M:%S')
        actual_span = (last_ts - first_ts).total_seconds()
        gap_stats = compute_gap_stats(window_records)
        charging_ratio = compute_charging_ratio(window_records)
        source_files = list(set(r['_source_file'] for r in window_records))
        window = {
            "window_id": f"win_{window_id:04d}",
            "time_range": {
                "start": window_records[0]['timestamp'],
                "end": window_records[-1]['timestamp']
            },
            "record_count": len(window_records),
            "actual_span_seconds": actual_span,
            "gap_stats": gap_stats,
            "charging_ratio": charging_ratio,
            "source_files": source_files,
            "records": window_records
        }
        windows.append(window)
        window_id += 1
        i += STEP_SIZE
    return windows

def save_windows_by_date(windows, output_dir):
    """按窗口第一条记录的日期分组保存到对应文件"""
    date_groups = defaultdict(list)
    for win in windows:
        date_key = win['time_range']['start'][:10]  # YYYY-MM-DD
        date_groups[date_key].append(win)
    total_windows = 0
    for date, wins in date_groups.items():
        output_file = output_dir / f"aggregated_{date}.jsonl"
        with open(output_file, 'w', encoding='utf-8') as f:
            for win in wins:
                # 移除内部records字段以减小文件体积，保留元数据
                win_out = {k: v for k, v in win.items() if k != 'records'}
                f.write(json.dumps(win_out, ensure_ascii=False) + '\n')
        total_windows += len(wins)
        print(f"✅ 结果已保存至: {output_file} (共 {len(wins)} 个窗口)")
    return total_windows

def main():
    print(f"当前工作目录: {Path.cwd()}")
    print(f"数据目录是否存在: {CLEANED_DIR.exists()}")
    # 加载数据
    all_records = load_all_records(CLEANED_DIR)
    if len(all_records) == 0:
        print("❌ 没有加载到任何记录，终止处理")
        return
    # 聚合窗口
    windows = aggregate_windows(all_records)
    print(f"共生成 {len(windows)} 个窗口")
    # 保存结果
    total_saved = save_windows_by_date(windows, AGGREGATED_DIR)
    print(f"🎉 聚合完成！共保存 {total_saved} 个窗口到 {AGGREGATED_DIR}")

if __name__ == "__main__":
    main()