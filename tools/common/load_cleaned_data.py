import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict
import sys

# 项目根目录 - 使用当前工作目录
PROJECT_ROOT = Path.cwd()
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "wearos_1"
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned" / "wearos_1"
AGGREGATED_DIR = PROJECT_ROOT / "data" / "aggregated" / "wearos_1"
TOOLS_DIR = PROJECT_ROOT / "tools" / "wearos_1"

print(f"当前工作目录: {PROJECT_ROOT}")
print(f"数据目录路径: {CLEANED_DIR}")
print(f"目录是否存在: {CLEANED_DIR.exists()}")

# 确保目录存在
AGGREGATED_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# 工具函数：加载所有清洗后的JSONL数据
def load_cleaned_data(cleaned_dir: Path):
    """加载指定目录下所有JSONL文件，返回记录列表（已排序）"""
    all_records = []
    files = sorted(cleaned_dir.glob("*.jsonl"))
    print(f"找到 {len(files)} 个JSONL文件")
    for f in files:
        print(f"  - {f.name}")
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"{file.name}: {len(lines)} 条记录")
            for line in lines:
                try:
                    record = json.loads(line.strip())
                    all_records.append(record)
                except json.JSONDecodeError as e:
                    print(f"  解析错误: {e}，跳过该行")
    # 打印第一条记录查看字段
    if all_records:
        print(f"第一条记录字段: {list(all_records[0].keys())}")
        print(f"第一条记录内容: {json.dumps(all_records[0], ensure_ascii=False)[:200]}")
    # 按时间排序
    all_records.sort(key=lambda x: x.get("timestamp", x.get("time", "")))
    print(f"共加载 {len(all_records)} 条记录")
    if len(all_records) == 0:
        print("⚠️ 警告：没有加载到任何数据，请检查文件格式")
    return all_records

def compute_gap_stats(records):
    """计算记录间隔统计信息"""
    if len(records) < 2:
        return {"min_gap": None, "max_gap": None, "avg_gap": None, "gap_count": 0, "gaps_over_30s": []}
    gaps = []
    for i in range(1, len(records)):
        t1 = datetime.strptime(records[i-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        t2 = datetime.strptime(records[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        gap = (t2 - t1).total_seconds()
        gaps.append(gap)
    gaps_over_30 = [g for g in gaps if g > 30]
    return {
        "min_gap": min(gaps) if gaps else None,
        "max_gap": max(gaps) if gaps else None,
        "avg_gap": round(sum(gaps)/len(gaps), 2) if gaps else None,
        "gap_count": len(gaps_over_30),
        "gaps_over_30s": gaps_over_30[:10]
    }

def compute_charging_ratio(records):
    """计算充电记录占比（心率字段为null视为充电）"""
    if not records:
        return 0.0
    charging_count = sum(1 for r in records if r.get("heart_rate") is None)
    return round(charging_count / len(records), 4)

def get_source_files(records):
    """获取记录来源文件列表（去重）"""
    sources = set()
    for r in records:
        src = r.get("source_file", "")
        if src:
            sources.add(src)
    return sorted(list(sources))

def aggregate_windows(records, window_size=20, step=10):
    """滑动窗口聚合，返回窗口列表"""
    windows = []
    total = len(records)
    if total == 0:
        return windows
    start_idx = 0
    window_id = 0
    while start_idx + window_size <= total:
        window_records = records[start_idx:start_idx + window_size]
        start_time = window_records[0]["timestamp"]
        end_time = window_records[-1]["timestamp"]
        dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        span_seconds = (dt_end - dt_start).total_seconds()
        gap_stats = compute_gap_stats(window_records)
        charging_ratio = compute_charging_ratio(window_records)
        source_files = get_source_files(window_records)
        window_meta = OrderedDict([
            ("window_id", f"W{window_id:04d}"),
            ("start_time", start_time),
            ("end_time", end_time),
            ("record_count", len(window_records)),
            ("actual_span_seconds", span_seconds),
            ("gap_stats", gap_stats),
            ("charging_ratio", charging_ratio),
            ("source_files", source_files)
        ])
        window_data = {
            "window_meta": window_meta,
            "records": window_records
        }
        windows.append(window_data)
        window_id += 1
        start_idx += step
    return windows

def save_windows_by_date(windows, output_dir: Path):
    """按窗口第一条记录的日期保存到对应文件"""
    date_groups = {}
    for w in windows:
        start_time = w["window_meta"]["start_time"]
        dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        date_key = dt.strftime("%Y-%m-%d")
        if date_key not in date_groups:
            date_groups[date_key] = []
        date_groups[date_key].append(w)
    for date_key, win_list in date_groups.items():
        output_file = output_dir / f"aggregated_{date_key}.jsonl"
        with open(output_file, 'w', encoding='utf-8') as f:
            for w in win_list:
                f.write(json.dumps(w, ensure_ascii=False) + '\n')
        print(f"✅ 结果已保存至: {output_file} (共 {len(win_list)} 个窗口)")

def main():
    print("="*60)
    print("开始加载清洗后的数据...")
    records = load_cleaned_data(CLEANED_DIR)
    if not records:
        print("❌ 没有加载到任何数据，终止处理。")
        return
    # 检查是否有timestamp字段
    if "timestamp" not in records[0]:
        print(f"⚠️ 记录中没有timestamp字段，可用字段: {list(records[0].keys())}")
        # 尝试使用time字段
        if "time" in records[0]:
            print("使用time字段作为timestamp")
            for r in records:
                r["timestamp"] = r["time"]
        else:
            print("❌ 无法找到时间字段，终止处理。")
            return
    print(f"数据时间范围: {records[0]['timestamp']} ~ {records[-1]['timestamp']}")
    print(f"总记录数: {len(records)}")
    print("="*60)
    print("开始滑动窗口聚合...")
    windows = aggregate_windows(records, window_size=20, step=10)
    print(f"共生成 {len(windows)} 个窗口")
    if windows:
        print(f"第一个窗口: {windows[0]['window_meta']['start_time']} ~ {windows[0]['window_meta']['end_time']}")
        print(f"最后一个窗口: {windows[-1]['window_meta']['start_time']} ~ {windows[-1]['window_meta']['end_time']}")
    print("="*60)
    print("按日期保存聚合结果...")
    save_windows_by_date(windows, AGGREGATED_DIR)
    print("="*60)
    print("✅ 聚合完成！")

if __name__ == "__main__":
    main()