# ./tools/wearos_1/jsonl_reader.py
# v2: 优化版本 - 增加数据预览、字段统计、类型推断、文件元数据功能

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

def read_first_jsonl(file_path: str) -> Optional[Dict[str, Any]]:
    """
    读取 JSONL 文件的第一条完整 JSON 记录
    
    Args:
        file_path: JSONL 文件路径
        
    Returns:
        第一条 JSON 记录（字典），如果文件为空或出错则返回 None
    """
    path = Path(file_path)
    
    # 验证文件存在
    if not path.exists():
        print(f"[ERROR] 文件不存在 - {file_path}")
        return None
    
    # 验证文件扩展名
    if path.suffix != '.jsonl':
        print(f"[WARN] 文件不是 .jsonl 格式 - {file_path}")
    
    # 尝试多种编码读取
    encodings = ['utf-8', 'utf-16', 'gbk', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(path, 'r', encoding=encoding) as f:
                first_line = f.readline()
                
                if not first_line.strip():
                    print(f"[ERROR] 文件为空 - {file_path}")
                    return None
                
                # 解析 JSON
                data = json.loads(first_line.strip())
                return data
                
        except UnicodeDecodeError:
            continue  # 尝试下一种编码
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON 解析错误: {e}")
            print(f"[INFO] 问题行内容: {first_line[:200]}...")
            return None
        except Exception as e:
            print(f"[ERROR] 读取文件时出错: {e}")
            return None
    
    print(f"[ERROR] 无法用任何编码读取文件 - {file_path}")
    return None

def list_jsonl_files(directory: str) -> List[str]:
    """
    列出目录下所有 JSONL 文件，按文件名排序
    
    Args:
        directory: 目录路径
        
    Returns:
        排序后的文件路径列表
    """
    path = Path(directory)
    if not path.exists():
        print(f"[ERROR] 目录不存在 - {directory}")
        return []
    
    files = sorted([f for f in path.glob('*.jsonl')])
    return [str(f) for f in files]

def get_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    获取文件元数据信息
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件元数据字典
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": "文件不存在"}
    
    # 统计行数
    line_count = 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for _ in f:
                line_count += 1
    except:
        pass
    
    return {
        "file_name": path.name,
        "file_size_bytes": path.stat().st_size,
        "file_size_kb": round(path.stat().st_size / 1024, 2),
        "line_count": line_count,
        "last_modified": str(path.stat().st_mtime)
    }

def analyze_field_types(data: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    """
    分析数据字段类型和结构
    
    Args:
        data: JSON 数据字典
        prefix: 字段前缀（用于嵌套字段）
        
    Returns:
        字段分析结果列表
    """
    fields = []
    
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        field_info = {
            "field": full_key,
            "type": type(value).__name__,
            "sample_value": str(value)[:50] if not isinstance(value, (dict, list)) else None,
            "is_nested": isinstance(value, (dict, list))
        }
        
        fields.append(field_info)
        
        # 递归分析嵌套字段
        if isinstance(value, dict):
            nested_fields = analyze_field_types(value, full_key)
            fields.extend(nested_fields)
        elif isinstance(value, list) and len(value) > 0:
            if isinstance(value[0], dict):
                nested_fields = analyze_field_types(value[0], f"{full_key}[0]")
                fields.extend(nested_fields)
            else:
                field_info["sample_value"] = f"[{type(value[0]).__name__} x {len(value)}]"
    
    return fields

def format_output(data: Dict[str, Any], file_path: str) -> str:
    """
    格式化输出结果
    
    Args:
        data: JSON 数据字典
        file_path: 文件路径
        
    Returns:
        格式化的输出文本
    """
    lines = []
    lines.append("=" * 70)
    lines.append(f"[INFO] 文件: {file_path}")
    
    # 文件元数据
    metadata = get_file_metadata(file_path)
    lines.append(f"[INFO] 文件大小: {metadata.get('file_size_kb', 'N/A')} KB")
    lines.append(f"[INFO] 总行数: {metadata.get('line_count', 'N/A')}")
    lines.append("=" * 70)
    
    # 字段分析
    fields = analyze_field_types(data)
    lines.append("")
    lines.append("[INFO] 字段结构分析:")
    lines.append("-" * 70)
    lines.append(f"{'字段名':<40} {'类型':<15} {'示例值'}")
    lines.append("-" * 70)
    for field in fields:
        if field['is_nested']:
            lines.append(f"{field['field']:<40} {field['type']:<15} (嵌套结构)")
        else:
            lines.append(f"{field['field']:<40} {field['type']:<15} {field['sample_value'] or 'N/A'}")
    
    # 完整数据
    lines.append("")
    lines.append("[INFO] 完整数据:")
    lines.append("-" * 70)
    lines.append(json.dumps(data, indent=2, ensure_ascii=False))
    
    # 数据摘要
    lines.append("")
    lines.append("[INFO] 数据摘要:")
    lines.append("-" * 70)
    lines.append(f"  - 顶级字段数: {len(data)}")
    lines.append(f"  - 嵌套字段数: {len(fields) - len(data)}")
    lines.append(f"  - 数据类型分布: {get_type_distribution(fields)}")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "".join(lines)

def get_type_distribution(fields: List[Dict[str, Any]]) -> str:
    """
    统计字段类型分布
    
    Args:
        fields: 字段分析结果列表
        
    Returns:
        类型分布字符串
    """
    type_count = {}
    for field in fields:
        if not field['is_nested']:
            t = field['type']
            type_count[t] = type_count.get(t, 0) + 1
    
    return ", ".join([f"{t}: {c}个" for t, c in sorted(type_count.items())])

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        result = read_first_jsonl(file_path)
        if result:
            print(format_output(result, file_path))
    else:
        print("用法: python jsonl_reader.py <jsonl_file_path>")
        print("示例: python jsonl_reader.py ./data/raw/wearos_1/2025-03-15.jsonl")
