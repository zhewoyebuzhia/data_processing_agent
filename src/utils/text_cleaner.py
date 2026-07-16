"""
文本清理工具
负责：移除非法字符、截断过大输入、估算Token数
"""
import re
import json
from typing import List, Dict, Union


class TextCleaner:
    """文本清理和预处理工具"""
    
    def __init__(self):
        pass
    
    def clean_text(self, text: str) -> str:
        """
        移除无效的 Unicode 代理字符（如 \udce4）
        
        Args:
            text: 待清理的文本
            
        Returns:
            清理后的文本
        """
        if not isinstance(text, str):
            return text
        # 移除所有代理字符（\ud800-\udfff）
        return re.sub(r'[\ud800-\udfff]', '', text)
    
    def truncate_large_input(self, user_input: str, max_chars: int = 8000) -> str:
        """
        裁剪过大的输入数据
        
        如果是 JSON 数组，只保留前 3 条作为示例
        如果是纯文本，保留前 max_chars 字符
        
        Args:
            user_input: 用户输入文本
            max_chars: 最大字符数限制
            
        Returns:
            裁剪后的文本
        """
        if len(user_input) <= max_chars:
            return user_input
        
        # 尝试解析 JSON
        try:
            data = json.loads(user_input)
            if isinstance(data, list) and len(data) > 3:
                # 只保留前3条作为示例
                sample = data[:3]
                truncated = (
                    f"数据格式示例（共{len(data)}条记录，此处仅显示前3条）：\n"
                    f"{json.dumps(sample, ensure_ascii=False, indent=2)}\n\n"
                    f"⚠️ 注意：完整数据共{len(data)}条，处理逻辑应适用于全部数据。"
                )
                return truncated
            elif isinstance(data, dict):
                # 字典类型，只保留键名
                keys = list(data.keys())
                truncated = f"数据对象，包含键: {keys}\n完整数据已在本地，请根据键名处理。"
                return truncated
        except json.JSONDecodeError:
            # 不是 JSON，截断文本
            truncated = user_input[:max_chars] + f"\n\n...（原输入共{len(user_input)}字符，已截断至{max_chars}字符）"
            return truncated
        
        return user_input
    
    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        估算消息的 Token 数量（粗略）
        
        Args:
            messages: 消息列表
            
        Returns:
            估算的 Token 数
        """
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, dict):
                total_chars += len(json.dumps(content, ensure_ascii=False))
        # 中英文混合粗略估算：约 2.5 字符/Token
        return int(total_chars / 2.5)