import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# ===== 路径配置 =====
PROJECT_ROOT = Path.cwd()
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned" / "wearos_1"
OUTPUT_DIR = PROJECT_ROOT / "data" / "aggregated" / "wearos_1"
TOOLS_DIR = PROJECT_ROOT / "tools" / "wearos_1"

# 确保输出目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

print(f"当前工作目录: {PROJECT_ROOT}")
print(f"清洗数据目录: {CLEANED_DIR}")
print(f"目录是否存在: {CLEANED_DIR.exists()}")
print(f"聚合输出目录: {OUTPUT_DIR}")

# ===== 第1步：加载所有清洗后的数据 =====
all_records = []
files = sorted(CLEANED_DIR.glob("*.jsonl"))
print(f"\n找到 {len(files)} 个JSONL文件")

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print(f"  {file.name}: {len(lines)} 条记录")
        for line in lines:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    all_records.append(record)
                except json.JSONDecodeError as e:
                    print(f"    ⚠️ JSON解析错误: {e}")

print(f"\n共加载 {len(all_records)} 条记录")

# ===== 第2步：按时间排序 =====
def parse_time(ts):
    """解析时间戳，支持多种格式"""
    if isinstance(ts, str):
        # 尝试常见格式
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
    return None

# 给每条记录添加解析后的时间
for r in all_records:
    ts = r.get("timestamp", r.get("time", ""))
    r["_dt"] = parse_time(ts)
    if r["_dt"] is None:
        print(f"  ⚠️ 无法解析时间: {ts}")

# 过滤掉时间解析失败的记录
all_records = [r for r in all_records if r["_dt"] is not None]
print(f"时间解析后有效记录: {len(all_records)} 条")

# 按时间排序
all_records.sort(key=lambda r: r["_dt"])

# 打印时间范围
if all_records:
    print(f"时间范围: {all_records[0]['_dt']} ~ {all_records[-1]['_dt']}")

# ===== 第3步：窗口聚合 =====
WINDOW_SIZE = 20
STEP_SIZE = 10

windows = []
window_id = 0
i = 0

while i + WINDOW_SIZE <= len(all_records):
    window_records = all_records[i:i + WINDOW_SIZE]
    
    # 窗口元数据
    first_ts = window_records[0]["_dt"]
    last_ts = window_records[-1]["_dt"]
    
    # 计算实际跨度（秒）
    actual_span = (last_ts - first_ts).total_seconds()
    
    # 计算间隔统计
    intervals = []
    for j in range(1, len(window_records)):
        gap = (window_records[j]["_dt"] - window_records[j-1]["_dt"]).total_seconds()
        intervals.append(gap)
    
    # 间隔统计
    if intervals:
        min_gap = min(intervals)
        max_gap = max(intervals)
        avg_gap = sum(intervals) / len(intervals)
        # 标记中断点（间隔>30秒）
        breaks = [idx for idx, g in enumerate(intervals) if g > 30]
    else:
        min_gap = 0
        max_gap = 0
        avg_gap = 0
        breaks = []
    
    # 计算充电占比（心率=null的占比）
    charging_count = sum(1 for r in window_records if r.get("heart_rate") is None)
    charging_ratio = charging_count / len(window_records) if window_records else 0
    
    # 获取来源文件列表
    source_files = list(set(r.get("source_file", r.get("file", "")) for r in window_records))
    
    # 确定窗口归属日期（以第一条记录的日期为准）
    window_date = first_ts.strftime("%Y-%m-%d")
    
    # 构建窗口数据
    window_data = {
        "window_id": f"window_{window_id:06d}",
        "window_date": window_date,
        "time_range": {
            "start": first_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "end": last_ts.strftime("%Y-%m-%d %H:%M:%S")
        },
        "record_count": len(window_records),
        "actual_span_seconds": actual_span,
        "gap_stats": {
            "min_gap_seconds": min_gap,
            "max_gap_seconds": max_gap,
            "avg_gap_seconds": round(avg_gap, 2),
            "break_indices": breaks,
            "break_count": len(breaks)
        },
        "charging_ratio": round(charging_ratio, 4),
        "source_files": list(set(source_files)),
        "records": []
    }
    
    # 添加记录数据（去掉_dt辅助字段）
    for r in window_records:
        record_copy = {k: v for k, v in r.items() if k != "_dt"}
        window_data["records"].append(record_copy)
    
    windows.append(window_data)
    window_id += 1
    i += STEP_SIZE

print(f"\n共生成 {len(windows)} 个窗口")

# ===== 第4步：按日期写入文件 =====
# 按日期分组
windows_by_date = defaultdict(list)
for w in windows:
    windows_by_date[w["window_date"]].append(w)

print(f"\n按日期分组:")
for date, wins in sorted(windows_by_date.items()):
    print(f"  {date}: {len(wins)} 个窗口")

# 写入每个日期的文件
total_written = 0
for date, wins in sorted(windows_by_date.items()):
    output_file = OUTPUT_DIR / f"aggregated_{date}.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for w in wins:
            f.write(json.dumps(w, ensure_ascii=False) + '\n')
    total_written += len(wins)
    print(f"  ✅ 写入 {output_file.name}: {len(wins)} 个窗口")

# 同时写入一个汇总文件
summary_file = OUTPUT_DIR / "aggregation_summary.json"
summary = {
    "total_records_processed": len(all_records),
    "total_windows": len(windows),
    "window_size": WINDOW_SIZE,
    "step_size": STEP_SIZE,
    "overlap_ratio": f"{STEP_SIZE/WINDOW_SIZE*100:.0f}%",
    "date_distribution": {date: len(wins) for date, wins in sorted(windows_by_date.items())},
    "time_range": {
        "start": all_records[0]["_dt"].strftime("%Y-%m-%d %H:%M:%S") if all_records else None,
        "end": all_records[-1]["_dt"].strftime("%Y-%m-%d %H:%M:%S") if all_records else None
    }
}
with open(summary_file, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n✅ 聚合完成！")
print(f"📊 共处理 {len(all_records)} 条记录，生成 {len(windows)} 个窗口")
print(f"📁 结果保存在: {OUTPUT_DIR}")
print(f"📄 汇总文件: {summary_file.name}")

# 列出输出目录
print(f"\n输出目录文件列表:")
for f in sorted(OUTPUT_DIR.glob("*")):
    size = f.stat().st_size
    print(f"  {f.name} ({size:,} bytes)")