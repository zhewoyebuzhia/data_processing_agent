#!/usr/bin/env python3
"""
充电记录提取工具 - 从wearos_1的JSONL文件中提取充电行为记录

功能：
1. 读取指定日期的JSONL文件
2. 筛选出behavior为"充电"的记录
3. 保存所有充电记录到cleaned目录
4. 打印第一条完整充电记录

用法：
    python charging_record_extractor.py [--date 20260421]
    
默认日期为20260421
"""

import json
import os
import sys
from pathlib import Path


def find_charging_records(input_file: str) -> list:
    """
    从JSONL文件中提取所有充电记录
    
    Args:
        input_file: JSONL文件路径
        
    Returns:
        充电记录列表
    """
    charging_records = []
    
    if not os.path.exists(input_file):
        print(f"错误：文件不存在 - {input_file}")
        return charging_records
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                
                # 检查是否为充电记录（多种匹配方式）
                is_charging = False
                
                # 方式1：检查timeline中的behavior字段
                if "timeline" in record and isinstance(record["timeline"], list):
                    for event in record["timeline"]:
                        if event.get("behavior") == "充电":
                            is_charging = True
                            break
                
                # 方式2：检查dominant_behavior字段
                if not is_charging and "statistics" in record:
                    stats = record["statistics"]
                    if stats.get("dominant_behavior") == "充电":
                        is_charging = True
                
                # 方式3：检查summary字段
                if not is_charging and "summary" in record:
                    if "充电" in record["summary"]:
                        is_charging = True
                
                if is_charging:
                    charging_records.append(record)
                    
            except json.JSONDecodeError as e:
                print(f"警告：第{line_num}行JSON解析失败 - {e}")
                continue
    
    return charging_records


def save_charging_records(records: list, output_file: str):
    """
    保存充电记录到文件
    
    Args:
        records: 充电记录列表
        output_file: 输出文件路径
    """
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已保存 {len(records)} 条充电记录到: {output_file}")


def print_first_record(records: list):
    """
    打印第一条完整充电记录
    
    Args:
        records: 充电记录列表
    """
    if not records:
        print("❌ 没有找到充电记录")
        return
    
    print("\n" + "="*80)
    print("📱 第一条充电记录（完整JSON）")
    print("="*80)
    print(json.dumps(records[0], ensure_ascii=False, indent=2))
    print("="*80)
    print(f"📊 共找到 {len(records)} 条充电记录")
    print(f"⏰ 时间范围: {records[0].get('timestamp_start')} ~ {records[-1].get('timestamp_end')}")


def main():
    """主函数"""
    # 默认日期
    date_str = "20260421"
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1].startswith("--date="):
            date_str = sys.argv[1].split("=")[1]
        elif sys.argv[1] == "--date" and len(sys.argv) > 2:
            date_str = sys.argv[2]
    
    # 构建文件路径
    input_file = f"data/raw/wearos_1/feature_{date_str}.jsonl"
    output_file = f"data/cleaned/wearos_1/charging_record_{date_str}.json"
    
    print(f"🔍 正在搜索充电记录...")
    print(f"📂 输入文件: {input_file}")
    print(f"📂 输出文件: {output_file}")
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"❌ 错误：输入文件不存在 - {input_file}")
        print("可用文件列表：")
        data_dir = "data/raw/wearos_1/"
        if os.path.exists(data_dir):
            for f in sorted(os.listdir(data_dir)):
                if f.endswith(".jsonl"):
                    print(f"  - {f}")
        sys.exit(1)
    
    # 提取充电记录
    charging_records = find_charging_records(input_file)
    
    if not charging_records:
        print("❌ 未找到任何充电记录")
        sys.exit(0)
    
    # 保存所有充电记录
    save_charging_records(charging_records, output_file)
    
    # 打印第一条完整记录
    print_first_record(charging_records)
    
    print(f"\n✅ 任务完成！")
    print(f"📁 所有充电记录已保存到: {output_file}")


if __name__ == "__main__":
    main()