"""
工具保存器
负责：保存生成的工具到 tools/ 目录，进行去重和版本管理
"""
import re
from pathlib import Path
from typing import Optional

from config.settings import TOOLS_DIR


class ToolSaver:
    """工具保存器"""
    
    def __init__(self):
        """初始化工具保存器"""
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def save_tool(self, code: str, device_name: str, tool_name: str = None, 
                  user_input: str = "") -> str:
        """
        保存生成的工具到 tools/{device_name}/ 目录
        
        Args:
            code: 工具代码
            device_name: 设备名称
            tool_name: 工具名称（可选，不提供则自动提取）
            user_input: 用户输入（辅助判断）
            
        Returns:
            保存的文件路径
        """
        # 确保设备目录存在
        tool_dir = TOOLS_DIR / device_name
        tool_dir.mkdir(parents=True, exist_ok=True)
        
        # 确定工具名称
        if not tool_name:
            tool_name = self._extract_tool_name(code, user_input)
        
        # 清理工具名：只保留字母数字和下划线
        tool_name = re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)
        filename = f"{tool_name}.py"
        tool_path = tool_dir / filename
        
        # 检查是否存在同名文件
        if tool_path.exists() and self.logger:
            self.logger.info(f"⚠️ 工具已存在，将覆盖: {tool_path}")
        
        # 写入文件
        with open(tool_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        if self.logger:
            self.logger.info(f"✅ 工具已保存: {tool_path}")
        
        return str(tool_path)
    
    def _extract_tool_name(self, code: str, user_input: str = "") -> str:
        """
        从代码中提取工具名称
        
        Args:
            code: 代码字符串
            user_input: 用户输入（辅助判断）
            
        Returns:
            建议的工具名称
        """
        # 从代码中提取函数名或类名
        func_match = re.search(r'def\s+(\w+)\s*\(', code)
        class_match = re.search(r'class\s+(\w+)\s*[:\(]', code)
        
        if func_match:
            tool_name = func_match.group(1)
        elif class_match:
            tool_name = class_match.group(1).lower()
        else:
            # 从用户输入或代码中提取任务类型
            if "清洗" in code or "clean" in code.lower():
                tool_name = "data_cleaner"
            elif "聚合" in code or "aggregate" in code.lower():
                tool_name = "data_aggregator"
            elif "分析" in code or "analyze" in code.lower():
                tool_name = "data_analyzer"
            else:
                tool_name = "data_processor"
        
        # 清理工具名：只保留字母数字和下划线
        return re.sub(r'[^a-zA-Z0-9_]', '_', tool_name)
    
    def delete_tool(self, device_name: str, tool_name: str) -> bool:
        """
        删除指定的工具文件
        
        Args:
            device_name: 设备名称
            tool_name: 工具名称（不含.py后缀）
            
        Returns:
            是否删除成功
        """
        tool_path = TOOLS_DIR / device_name / f"{tool_name}.py"
        if not tool_path.exists():
            if self.logger:
                self.logger.warning(f"工具不存在: {tool_path}")
            return False
        
        try:
            tool_path.unlink()
            if self.logger:
                self.logger.info(f"🗑️ 已删除工具: {tool_path}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"删除工具失败: {e}")
            return False
    
    def tool_exists(self, device_name: str, tool_name: str) -> bool:
        """
        检查工具是否存在
        
        Args:
            device_name: 设备名称
            tool_name: 工具名称（不含.py后缀）
            
        Returns:
            是否存在
        """
        tool_path = TOOLS_DIR / device_name / f"{tool_name}.py"
        return tool_path.exists()