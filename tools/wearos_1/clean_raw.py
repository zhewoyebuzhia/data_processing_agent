#!/usr/bin/env python3
"""
wearos_1 数据清洗工具
清洗规则：
1. 只保留 timestamp_start 和 timestamp_end，删除其他所有时间字段
2. 当 charging_seconds=30 时，将所有心率相关字段置为 null
3. 删除规则引擎添加的字段，保留原始传感器数据

输出格式：
{
    "start_time": "2026-04-17 00:02:39",
    "end_time": "2026-04-17 00:03:10",
    "duration_seconds": 30,
    "charging_seconds": 0,
    "user_id": "004",
    "sensors": {
        "heart_rate": {"avg": 78.53, "min": 73, "max": 82},
        "light": 0,
        "accelerometer": {"avg_magnitude": 9.70, "variance": 0.0012},
        "gps": {"has_fix": false, "point_count": 0},
        "compass": {"avg_azimuth": 158.23, "direction_changes": 1}
    }
}

v1: 初始版本
"""

import json
import os
import sys
from pathlib import Path


def get_project_root():
    """获取项目根目录 - 使用当前工作目录"""
    return Path.cwd()


def clean_record(record):
    """
    清洗单条记录
    
    清洗规则：
    1. 只保留 timestamp_start 和 timestamp_end，重命名为 start_time 和 end_time
    2. 当 charging_seconds=30 时，将所有心率相关字段置为 null
    3. 删除规则引擎添加的字段
    """
    cleaned = {}
    
    # 规则1：只保留时间戳字段，重命名
    cleaned["start_time"] = record.get("timestamp_start", "")
    cleaned["end_time"] = record.get("timestamp_end", "")
    
    # 保留基础字段
    cleaned["duration_seconds"] = record.get("duration_seconds", 0)
    cleaned["charging_seconds"] = record.get("charging_seconds", 0)
    cleaned["user_id"] = record.get("user_id", "")
    
    # 构建 sensors 字段
    sensors = {}
    
    # 处理心率数据
    statistics = record.get("statistics", {})
    heart_rate = statistics.get("heart_rate", {})
    
    # 规则2：当 charging_seconds=30 时，心率置为 null
    if record.get("charging_seconds") == 30:
        sensors["heart_rate"] = None
    else:
        # 只保留数值型心率数据
        hr_clean = {}
        if isinstance(heart_rate, dict):
            for key in ["avg", "min", "max"]:
                if key in heart_rate:
                    hr_clean[key] = heart_rate[key]
        sensors["heart_rate"] = hr_clean if hr_clean else None
    
    # 处理光照数据 - 只保留 avg 数值
    light = statistics.get("light", {})
    if isinstance(light, dict):
        sensors["light"] = light.get("avg", 0)
    else:
        sensors["light"] = light if isinstance(light, (int, float)) else 0
    
    # 处理加速度计数据
    accelerometer = statistics.get("accelerometer", {})
    if isinstance(accelerometer, dict):
        acc_clean = {}
        for key in ["avg_magnitude", "variance"]:
            if key in accelerometer:
                acc_clean[key] = accelerometer[key]
        sensors["accelerometer"] = acc_clean if acc_clean else None
    else:
        sensors["accelerometer"] = None
    
    # 处理GPS数据
    gps = statistics.get("gps", {})
    if isinstance(gps, dict):
        gps_clean = {}
        for key in ["has_fix", "point_count"]:
            if key in gps:
                gps_clean[key] = gps[key]
        sensors["gps"] = gps_clean if gps_clean else None
    else:
        sensors["gps"] = None
    
    # 处理指南针数据
    compass = statistics.get("compass", {})
    if isinstance(compass, dict):
        compass_clean = {}
        for key in ["avg_azimuth", "direction_changes"]:
            if key in compass:
                compass_clean[key] = compass[key]
        sensors["compass"] = compass_clean if compass_clean else None
    else:
        sensors["compass"] = None
    
    # 处理WiFi数据 - 只保留 top_signals
    wifi = statistics.get("wifi", {})
    if isinstance(wifi, dict):
        wifi_clean = {}
        if "top_signals" in wifi:
            wifi_clean["top_signals"] = wifi["top_signals"]
        sensors["wifi"] = wifi_clean if wifi_clean else None
    else:
        sensors["wifi"] = None
    
    cleaned["sensors"] = sensors
    
    return cleaned


def clean_file(input_path, output_path):
    """
    清洗单个JSONL文件
    
    返回统计信息
    """
    stats = {
        "file": input_path.name,
        "total_records": 0,
        "cleaned_records": 0,
        "charging_records": 0,
        "heart_rate_nullified": 0,
        "errors": 0
    }
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f_in:
            with open(output_path, 'w', encoding='utf-8') as f_out:
                for line_num, line in enumerate(f_in, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    stats["total_records"] += 1
                    
                    try:
                        record = json.loads(line)
                        cleaned = clean_record(record)
                        
                        # 统计充电记录
                        if record.get("charging_seconds") == 30:
                            stats["charging_records"] += 1
                            stats["heart_rate_nullified"] += 1
                        
                        f_out.write(json.dumps(cleaned, ensure_ascii=False) + '\n')
                        stats["cleaned_records"] += 1
                        
                    except json.JSONDecodeError as e:
                        stats["errors"] += 1
                        print(f"  [警告] 文件 {input_path.name} 第 {line_num} 行 JSON 解析错误: {e}")
                    except Exception as e:
                        stats["errors"] += 1
                        print(f"  [警告] 文件 {input_path.name} 第 {line_num} 行处理错误: {e}")
        
        return stats
        
    except FileNotFoundError:
        print(f"  [错误] 文件不存在: {input_path}")
        return None
    except Exception as e:
        print(f"  [错误] 读取文件 {input_path.name} 失败: {e}")
        return None


def main():
    """主函数：清洗所有JSONL文件"""
    project_root = get_project_root()
    
    # 输入输出目录
    raw_dir = project_root / "data" / "raw" / "wearos_1"
    cleaned_dir = project_root / "data" / "cleaned" / "wearos_1"
    
    # 确保输出目录存在
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有JSONL文件
    jsonl_files = sorted(raw_dir.glob("feature_*.jsonl"))
    
    if not jsonl_files:
        print(f"未在 {raw_dir} 找到任何 feature_*.jsonl 文件")
        return
    
    print(f"找到 {len(jsonl_files)} 个JSONL文件待清洗\n")
    
    # 汇总统计
    total_stats = {
        "total_files": len(jsonl_files),
        "total_records": 0,
        "total_cleaned": 0,
        "total_charging": 0,
        "total_heart_nullified": 0,
        "total_errors": 0
    }
    
    # 逐文件清洗
    for file_path in jsonl_files:
        output_path = cleaned_dir / file_path.name
        
        print(f"正在清洗: {file_path.name}")
        stats = clean_file(file_path, output_path)
        
        if stats:
            print(f"  ✓ 完成: {stats['total_records']} 条记录, "
                  f"{stats['charging_records']} 条充电记录, "
                  f"{stats['heart_rate_nullified']} 条心率置空, "
                  f"{stats['errors']} 个错误")
            
            total_stats["total_records"] += stats["total_records"]
            total_stats["total_cleaned"] += stats["cleaned_records"]
            total_stats["total_charging"] += stats["charging_records"]
            total_stats["total_heart_nullified"] += stats["heart_rate_nullified"]
            total_stats["total_errors"] += stats["errors"]
        else:
            print(f"  ✗ 失败")
    
    # 输出汇总统计
    print("\n" + "=" * 60)
    print("清洗完成！汇总统计：")
    print(f"  处理文件数:     {total_stats['total_files']}")
    print(f"  总记录数:       {total_stats['total_records']}")
    print(f"  清洗记录数:     {total_stats['total_cleaned']}")
    print(f"  充电记录数:     {total_stats['total_charging']}")
    print(f"  心率置空数:     {total_stats['total_heart_nullified']}")
    print(f"  错误数:         {total_stats['total_errors']}")
    print("=" * 60)
    print(f"\n清洗后数据保存在: {cleaned_dir}")


if __name__ == "__main__":
    main()