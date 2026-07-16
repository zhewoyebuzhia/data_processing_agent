"""
工具扫描器
负责：扫描 tools/ 目录，获取所有工具脚本信息
"""
from pathlib import Path
from typing import List, Dict

from config.settings import TOOLS_DIR


class ToolScanner:
    """工具目录扫描器"""
    
    def __init__(self):
        """
        初始化工具扫描器
        
        Args:
            logger: 日志记录器（可选）
        """
        self.tools_cache: List[Dict[str, str]] = []
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def scan(self) -> None:
        """
        扫描 tools/ 目录，获取所有 .py 工具脚本
        更新 tools_cache
        """
        self.tools_cache = []
        if not TOOLS_DIR.exists():
            if self.logger:
                self.logger.warning(f"工具目录不存在: {TOOLS_DIR}")
            return
        
        for py_file in TOOLS_DIR.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            rel_path = py_file.relative_to(TOOLS_DIR)
            self.tools_cache.append({
                "name": py_file.stem,
                "path": str(rel_path),
                "full_path": str(py_file),
                "device": rel_path.parent.name if rel_path.parent != Path(".") else "root"
            })
        
        self.tools_cache.sort(key=lambda x: (x["device"], x["name"]))
        
        if self.logger:
            self.logger.debug(f"扫描到 {len(self.tools_cache)} 个工具")
    
    def get_description(self) -> str:
        """
        生成工具列表描述，供 LLM 参考
        
        Returns:
            格式化的工具列表描述
        """
        if not self.tools_cache:
            return "（当前没有可用工具）"
        
        lines = ["当前可用工具列表："]
        current_device = None
        for tool in self.tools_cache:
            if tool["device"] != current_device:
                current_device = tool["device"]
                lines.append(f"\n  📁 {current_device}/")
            lines.append(f"    - {tool['name']}.py")
        return "\n".join(lines)
    
    def get_cache(self) -> List[Dict[str, str]]:
        """
        获取工具缓存
        
        Returns:
            工具列表
        """
        return self.tools_cache
    
    def get_tool_count(self) -> int:
        """
        获取工具数量
        
        Returns:
            工具数量
        """
        return len(self.tools_cache)
    
    def get_tools_by_device(self, device_name: str) -> List[Dict[str, str]]:
        """
        获取指定设备的工具列表
        
        Args:
            device_name: 设备名称
            
        Returns:
            该设备下的工具列表
        """
        return [t for t in self.tools_cache if t["device"] == device_name]
    
    def find_tool(self, tool_name: str) -> Dict[str, str]:
        """
        查找指定名称的工具
        
        Args:
            tool_name: 工具名称（不含.py后缀）
            
        Returns:
            工具信息字典，如果未找到返回 None
        """
        for tool in self.tools_cache:
            if tool["name"] == tool_name:
                return tool
        return None