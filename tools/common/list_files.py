# ./tools/wearos_1/jsonl_reader.py
import json
import os
from pathlib import Path

def get_project_root():
    """获取项目根目录（data_processing_agent 所在目录）"""
    # 优先使用当前工作目录
    cwd = Path(os.getcwd())
    
    # 检查当前目录是否包含 data 和 tools 子目录
    if (cwd / "data").exists() and (cwd / "tools").exists():
        return cwd
    
    # 如果当前目录是 tools/wearos_1，则向上两级
    if cwd.name == "wearos_1" and cwd.parent.name == "tools":
        return cwd.parent.parent
    
    # 如果当前目录是 tools，则向上一级
    if cwd.name == "tools":
        return cwd.parent
    
    # 如果当前目录是 data_processing_agent，直接返回
    if cwd.name == "data_processing_agent":
        return cwd
    
    # 最后尝试从脚本位置推断
    script_path = Path(__file__).resolve()
    # 检查脚本是否在 tools/wearos_1/ 下
    if "tools" in script_path.parts and "wearos_1" in script_path.parts:
        # 找到 tools 目录的父目录
        tools_index = script_path.parts.index("tools")
        root_parts = script_path.parts[:tools_index]
        return Path(*root_parts)
    
    return cwd

def read_first_jsonl_line(file_path):
    """
    读取 JSONL 文件的第一行并返回解析后的 JSON 对象
    
    Args:
        file_path: JSONL 文件路径（可以是相对路径或绝对路径）
        
    Returns:
        dict: 解析后的 JSON 数据
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    if file_path.suffix != '.jsonl':
        raise ValueError(f"文件格式错误，需要 .jsonl 文件: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        
    if not first_line.strip():
        raise ValueError(f"文件为空: {file_path}")
    
    try:
        data = json.loads(first_line)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}")

def format_json(data, indent=2):
    """格式化 JSON 数据为可读字符串"""
    return json.dumps(data, indent=indent, ensure_ascii=False)

if __name__ == "__main__":
    # 测试运行
    print(f"当前工作目录: {os.getcwd()}")
    print(f"脚本所在目录: {Path(__file__).resolve().parent}")
    
    # 获取项目根目录
    root = get_project_root()
    print(f"项目根目录: {root}")
    
    # 构建数据文件路径
    file_path = root / "data/raw/wearos_1/feature_20260415.jsonl"
    print(f"数据文件路径: {file_path}")
    print(f"文件是否存在: {file_path.exists()}")
    
    if file_path.exists():
        data = read_first_jsonl_line(file_path)
        print("\n=== 第一条 JSON 数据 ===")
        print(format_json(data))
    else:
        print("\n❌ 文件不存在，请检查路径")
        # 列出 data/raw/wearos_1/ 目录下的文件
        data_dir = root / "data/raw/wearos_1"
        if data_dir.exists():
            print(f"\n{data_dir} 目录下的文件:")
            for f in sorted(data_dir.iterdir()):
                print(f"  - {f.name}")