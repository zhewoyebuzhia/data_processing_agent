"""
代码解析工具
负责：提取代码块、解析DSML格式、提取期望输出路径、提取工具名称
"""
import re
from typing import Optional, Dict, List


class CodeParser:
    """代码解析和提取工具"""
    
    def __init__(self):
        pass
    
    def extract_code(self, text: str) -> Optional[str]:
        """
        从 LLM 回复中提取代码块
        
        支持：
        - Python 代码块（```python）
        - 普通代码块（```）
        - Bash 代码块（```bash 或 <bash>）
        
        Args:
            text: LLM 回复文本
            
        Returns:
            提取的代码，如果是 Bash 则返回 "__BASH__:命令"
        """
        # 1. 优先检查 Python 代码块
        patterns = [
            r'```python\s*\n(.*?)```',  # 标准格式
            r'```python(.*?)```',        # 无换行
            r'```\s*\n(.*?)```',         # 普通代码块
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                code = match.group(1).strip()
                # 如果提取的代码中还有代码块标记，递归提取
                if '```python' in code or '```' in code:
                    # 尝试提取嵌套的 python 代码块
                    inner_match = re.search(r'```python\s*\n(.*?)```', code, re.DOTALL)
                    if inner_match:
                        return inner_match.group(1).strip()
                    # 尝试普通代码块
                    inner_match = re.search(r'```\s*\n(.*?)```', code, re.DOTALL)
                    if inner_match:
                        return inner_match.group(1).strip()
                return code
        
        # 2. 检查 Bash 代码块
        bash_patterns = [
            r'```bash\s*\n(.*?)```',
            r'<bash>\s*(.*?)\s*</bash>',
        ]
        for pattern in bash_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return f"__BASH__:{match.group(1).strip()}"
        
        # 3. 如果没有代码块标记，检查内容是否看起来像 Python 代码
        lines = text.strip().split('\n')
        if lines and any(line.strip().startswith(('import ', 'from ', 'def ', 'class ')) for line in lines[:5]):
            return text.strip()
        
        return None
    
    def clean_code(self, code: str) -> str:
        """
        清理提取的代码，移除残留的 markdown 标记
        
        Args:
            code: 原始提取的代码
            
        Returns:
            清理后的代码
        """
        if not code:
            return code
        
        # 移除开头的 ```python 或 ```
        code = re.sub(r'^```python\s*\n?', '', code)
        code = re.sub(r'^```\s*\n?', '', code)
        # 移除结尾的 ```
        code = re.sub(r'\n?```$', '', code)
        
        # 如果代码中还包含 ```python，尝试提取真正的代码
        if '```python' in code:
            match = re.search(r'```python\s*\n(.*?)```', code, re.DOTALL)
            if match:
                code = match.group(1).strip()
        
        # 如果代码中还包含 ```，尝试提取
        if '```' in code:
            match = re.search(r'```\s*\n(.*?)```', code, re.DOTALL)
            if match:
                code = match.group(1).strip()
        
        return code
    
    def parse_dsml_tools(self, text: str) -> Optional[Dict]:
        """
        解析 DSML 格式的工具调用
        
        Returns:
            {"type": "bash"|"python", "command": "..."} 或 None
        """
        # 匹配完整的 DSML 工具调用块
        tool_pattern = r'<｜DSML｜tool_calls>(.*?)</｜DSML｜tool_calls>'
        match = re.search(tool_pattern, text, re.DOTALL)
        if not match:
            return None
        
        tool_content = match.group(1)
        
        # 提取 Bash 命令
        bash_match = re.search(
            r'<｜DSML｜invoke name="bash">.*?<｜DSML｜parameter name="command" string="true">(.*?)</｜DSML｜parameter>.*?</｜DSML｜invoke>',
            tool_content,
            re.DOTALL
        )
        if bash_match:
            return {"type": "bash", "command": bash_match.group(1).strip()}
        
        # 提取 Python 代码
        python_match = re.search(
            r'<｜DSML｜invoke name="python">.*?<｜DSML｜parameter name="code" string="true">(.*?)</｜DSML｜parameter>.*?</｜DSML｜invoke>',
            tool_content,
            re.DOTALL
        )
        if python_match:
            return {"type": "python", "code": python_match.group(1).strip()}
        
        return None
    
    def extract_expected_outputs(self, code: str, user_input: str) -> List[str]:
        """
        从代码和用户输入中提取预期的输出路径
        
        Args:
            code: 代码字符串
            user_input: 用户输入
            
        Returns:
            预期的输出路径列表
        """
        expected = []
        
        # 从代码中提取 write/open 路径
        write_patterns = [
            r'open\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
            r'write\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
            r'dump\s*\([^,]+,\s*open\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
            r'to_json\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
            r'save\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
        ]
        for pattern in write_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            expected.extend(matches)
        
        # 从用户输入中提取目标路径
        clean_match = re.search(r'保存到\s*([^\s,，。]+)', user_input)
        if clean_match:
            expected.append(clean_match.group(1))
        
        # 去重
        return list(set(expected))
    
    def extract_tool_name(self, code: str, user_input: str = "") -> str:
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