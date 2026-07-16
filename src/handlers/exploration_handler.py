"""
探索任务处理器
负责：处理探索类任务（使用 Bash 命令）
"""
import re
from typing import Dict, List, Optional


class ExplorationHandler:
    """探索任务处理器"""
    
    def __init__(self, llm_client, code_executor, context_manager, 
                 tool_scanner, text_cleaner, code_parser):
        """
        初始化探索任务处理器
        
        Args:
            llm_client: LLM客户端实例
            code_executor: 代码执行器实例
            context_manager: 上下文管理器实例
            tool_scanner: 工具扫描器实例
            text_cleaner: 文本清理器实例
            code_parser: 代码解析器实例
        """
        self.llm_client = llm_client
        self.code_executor = code_executor
        self.context_manager = context_manager
        self.tool_scanner = tool_scanner
        self.text_cleaner = text_cleaner
        self.code_parser = code_parser
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def handle(self, user_input: str) -> str:
        """
        处理探索类任务
        
        Args:
            user_input: 用户输入
            
        Returns:
            执行结果
        """
        if self.logger:
            self.logger.info("🔍 探索任务模式")
        
        # 清理输入
        cleaned_input = self.text_cleaner.clean_text(user_input)
        cleaned_input = self.text_cleaner.truncate_large_input(cleaned_input, max_chars=8000)
        
        # 添加到对话历史
        self.context_manager.add_user_message(cleaned_input)
        
        # 构建消息
        messages = [
            {"role": "system", "content": "你是一个助手，可以用 Bash 命令查看文件系统。"},
            {"role": "system", "content": "优先使用 bash 命令（ls、cat、head、find、grep）来探索文件系统。"},
            {"role": "system", "content": f"当前可用工具：\n{self.tool_scanner.get_description()}"},
        ] + self.context_manager.get_history()
        
        # 调用LLM
        result = self.llm_client.call_llm(messages, temperature=0.1)
        
        if "error" in result:
            error_msg = f"❌ LLM 调用失败: {result['error']}"
            if self.logger:
                self.logger.error(error_msg)
            return error_msg
        
        try:
            assistant_reply = result["choices"][0]["message"]["content"]
            assistant_reply = self.text_cleaner.clean_text(assistant_reply)
            if self.logger:
                self.logger.info(f"📝 LLM 回复:\n{assistant_reply[:500]}...")
            
            # 尝试解析多个 DSML 工具调用
            dsml_results = self._parse_multiple_dsml_tools(assistant_reply)
            
            if dsml_results:
                all_outputs = []
                for dsml_result in dsml_results:
                    if dsml_result["type"] == "bash":
                        bash_cmd = dsml_result["command"]
                        if self.logger:
                            self.logger.info(f"🔧 执行 Bash: {bash_cmd}")
                        success, output = self.code_executor.execute_bash_command(bash_cmd)
                        if success:
                            all_outputs.append(f"✅ {bash_cmd}\n{output}")
                        else:
                            all_outputs.append(f"❌ {bash_cmd}\n{output}")
                    elif dsml_result["type"] == "python":
                        # 探索模式下也支持 Python（但优先用 Bash）
                        if self.logger:
                            self.logger.info(f"🔧 执行 Python 代码")
                        success, output, _ = self.code_executor.execute_python_code(dsml_result["code"])
                        if success:
                            all_outputs.append(f"✅ Python 执行成功\n{output}")
                        else:
                            all_outputs.append(f"❌ Python 执行失败\n{output}")
                
                if all_outputs:
                    result_msg = "\n\n".join(all_outputs)
                    if len(result_msg) > 2000:
                        result_msg = result_msg[:2000] + "\n...(输出已截断)"
                    self.context_manager.add_assistant_message(result_msg)
                    return result_msg
            
            # 如果没有 DSML 调用，尝试提取单个 Bash 代码块
            code = self.code_parser.extract_code(assistant_reply)
            if code and code.startswith("__BASH__:"):
                bash_cmd = code.replace("__BASH__:", "").strip()
                if self.logger:
                    self.logger.info(f"🔧 执行 Bash: {bash_cmd}")
                success, output = self.code_executor.execute_bash_command(bash_cmd)
                if success:
                    result_msg = f"✅ 执行结果：\n{output[:2000]}"
                    self.context_manager.add_assistant_message(result_msg)
                    return result_msg
                else:
                    result_msg = f"❌ 执行失败：\n{output}"
                    self.context_manager.add_assistant_message(result_msg)
                    return result_msg
            
            # 纯文本回复
            self.context_manager.add_assistant_message(assistant_reply)
            return assistant_reply
            
        except (KeyError, IndexError) as e:
            error_msg = f"❌ 解析 LLM 响应失败: {result}"
            if self.logger:
                self.logger.error(error_msg)
            return error_msg
    
    def _parse_multiple_dsml_tools(self, text: str) -> List[Dict]:
        """
        解析多个 DSML 格式的工具调用
        
        Args:
            text: LLM 回复文本
            
        Returns:
            工具调用列表
        """
        results = []
        
        # 匹配完整的 DSML 工具调用块
        tool_pattern = r'<｜DSML｜tool_calls>(.*?)</｜DSML｜tool_calls>'
        match = re.search(tool_pattern, text, re.DOTALL)
        if not match:
            return results
        
        tool_content = match.group(1)
        
        # 提取所有 Bash 命令
        bash_matches = re.findall(
            r'<｜DSML｜invoke name="bash">.*?<｜DSML｜parameter name="command" string="true">(.*?)</｜DSML｜parameter>.*?</｜DSML｜invoke>',
            tool_content,
            re.DOTALL
        )
        for bash_cmd in bash_matches:
            results.append({"type": "bash", "command": bash_cmd.strip()})
        
        # 提取所有 Python 代码
        python_matches = re.findall(
            r'<｜DSML｜invoke name="python">.*?<｜DSML｜parameter name="code" string="true">(.*?)</｜DSML｜parameter>.*?</｜DSML｜invoke>',
            tool_content,
            re.DOTALL
        )
        for python_code in python_matches:
            results.append({"type": "python", "code": python_code.strip()})
        
        return results