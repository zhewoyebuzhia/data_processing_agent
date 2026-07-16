"""
数据处理任务处理器
负责：处理数据处理任务，生成并执行Python代码，迭代优化
"""
from typing import Dict, List, Optional
import ast
import re

from config.settings import MAX_PROCESSING_ITERATIONS


class ProcessingHandler:
    """数据处理任务处理器"""
    
    def __init__(self, llm_client, code_executor, context_manager, 
                 tool_scanner, tool_saver, text_cleaner, code_parser, 
                 result_validator):
        """
        初始化数据处理任务处理器
        
        Args:
            llm_client: LLM客户端实例
            code_executor: 代码执行器实例
            context_manager: 上下文管理器实例
            tool_scanner: 工具扫描器实例
            tool_saver: 工具保存器实例
            text_cleaner: 文本清理器实例
            code_parser: 代码解析器实例
            result_validator: 结果验证器实例
        """
        self.llm_client = llm_client
        self.code_executor = code_executor
        self.context_manager = context_manager
        self.tool_scanner = tool_scanner
        self.tool_saver = tool_saver
        self.text_cleaner = text_cleaner
        self.code_parser = code_parser
        self.result_validator = result_validator
        self.logger = None
        self.system_prompt = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def set_system_prompt(self, system_prompt: str):
        """设置系统提示词"""
        self.system_prompt = system_prompt
    
    def _validate_syntax(self, code: str) -> tuple:
        """
        使用 ast 检查 Python 代码语法
        
        Returns:
            (是否有效, 错误信息)
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            # 提取错误行号和上下文
            error_msg = f"语法错误 (行 {e.lineno}): {e.msg}\n"
            # 显示错误行附近的代码
            lines = code.split('\n')
            if e.lineno and 1 <= e.lineno <= len(lines):
                error_line = lines[e.lineno - 1]
                error_msg += f"错误行: {error_line}\n"
                # 显示前后各2行
                start = max(0, e.lineno - 3)
                end = min(len(lines), e.lineno + 2)
                error_msg += "附近代码:\n"
                for i in range(start, end):
                    prefix = ">>> " if i == e.lineno - 1 else "    "
                    error_msg += f"{prefix}{i+1}: {lines[i]}\n"
            return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def _has_write_operation(self, code: str) -> bool:
        """
        检查代码中是否包含文件写入操作
        
        Args:
            code: Python代码字符串
            
        Returns:
            是否包含写入操作
        """
        write_patterns = [
            r'\.write\s*\(',
            r'json\.dump\s*\(',
            r'to_json\s*\(',
            r'\.save\s*\(',
            r'w\+?\'\s*[,)]',
            r'wb\'?\s*[,)]',
        ]
        for pattern in write_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return False
    
    def _detect_write_target(self, code: str) -> Optional[str]:
        """
        从代码中检测写入目标路径
        
        Args:
            code: Python代码字符串
            
        Returns:
            检测到的写入目标路径，或 None
        """
        patterns = [
            r'open\s*\(\s*["\']([^"\']+\.jsonl?)["\']',
            r'open\s*\(\s*["\']([^"\']+\.json)["\']',
            r'open\s*\(\s*["\']([^"\']+\.csv)["\']',
            r'to_json\s*\(\s*["\']([^"\']+)["\']',
            r'\.save\s*\(\s*["\']([^"\']+)["\']',
            r'dump\s*\([^,]+,\s*open\s*\(\s*["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, code, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def _build_write_template(self, user_input: str) -> str:
        """
        根据用户输入构建写入代码模板
        
        Args:
            user_input: 用户输入
            
        Returns:
            写入代码模板
        """
        device = self._detect_device(user_input)
        return f"""
# ===== 写入结果到 data/aggregated/{device}/ 目录 =====
# 示例代码（请根据实际数据结构调整）：
output_dir = PROJECT_ROOT / "data" / "aggregated" / "{device}"
output_dir.mkdir(parents=True, exist_ok=True)

# 方式1：写入 JSONL 文件
output_file = output_dir / "aggregated_result.jsonl"
with open(output_file, 'w', encoding='utf-8') as f:
    for record in processed_data:  # 替换为你的数据变量名
        f.write(json.dumps(record, ensure_ascii=False) + '\\n')
print(f"✅ 结果已保存至: {{output_file}}")

# 方式2：写入 JSON 文件
output_file = output_dir / "aggregated_result.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(processed_data, f, ensure_ascii=False, indent=2)
print(f"✅ 结果已保存至: {{output_file}}")
"""
    
    def handle(self, user_input: str, max_iterations: int = MAX_PROCESSING_ITERATIONS) -> str:
        """
        处理数据处理任务
        
        Args:
            user_input: 用户输入
            max_iterations: 最大迭代次数
            
        Returns:
            执行结果
        """
        if self.logger:
            self.logger.info("📊 数据处理任务模式")
        
        # 清理输入
        cleaned_input = self.text_cleaner.clean_text(user_input)
        cleaned_input = self.text_cleaner.truncate_large_input(cleaned_input, max_chars=8000)
        
        # 添加到对话历史
        self.context_manager.add_user_message(cleaned_input)
        
        # 检查是否需要压缩上下文
        if self.context_manager.should_compress():
            self.context_manager.compress_context(self.llm_client)
        
        # 检测设备名称
        device_name = self._detect_device(user_input)
        
        # 构建消息
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": f"当前可用工具：\n{self.tool_scanner.get_description()}"},
            {"role": "system", "content": f"""
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ 强制指令 - 只输出 Python 代码                          ║
╠══════════════════════════════════════════════════════════════╣
║  1. 必须用 ```python 代码块包裹完整的 Python 代码          ║
║  2. 不要输出任何解释、步骤描述或对话内容                    ║
║  3. 不要使用 DSML 或任何工具调用格式                       ║
║  4. 代码必须包含：读取 → 处理 → 写入 → 打印统计           ║
║  5. 🔥 必须将处理结果写入 data/aggregated/{device_name}/  ║
║  6. 禁止只做"加载+打印"，必须包含写入操作                  ║
║  7. 如果用户问"介绍工具"或"查看目录"，请直接生成代码演示   ║
╚══════════════════════════════════════════════════════════════╝
"""},
            {"role": "system", "content": f"""
📁 当前数据目录：
- 清洗后数据：data/cleaned/{device_name}/
- 聚合输出：data/aggregated/{device_name}/
- 工具目录：tools/{device_name}/

⚠️ 请确保写入路径使用 data/aggregated/{device_name}/，不要使用 data/aggregated/common/。
"""},
        ] + self.context_manager.get_history()
        
        iteration = 0
        last_code = None
        last_error = None
        saved_tool_path = None
        no_write_warning_count = 0  # 记录连续无写入操作的次数
        
        while iteration < max_iterations:
            iteration += 1
            if self.logger:
                self.logger.info(f"\n{'='*50}")
                self.logger.info(f"🔄 第 {iteration}/{max_iterations} 次尝试")
                self.logger.info(f"{'='*50}")
            
            # 如果是第 3 次或以上迭代，且之前有"无写入"警告，在 user 消息中强化要求
            if iteration >= 3 and no_write_warning_count >= 1:
                # 在消息中插入强化指令
                write_template = self._build_write_template(user_input)
                strong_feedback = f"""
⚠️⚠️⚠️ 你已经多次生成没有写入操作的代码！⚠️⚠️⚠️

数据处理任务必须将结果写入文件，不能只是打印输出。

请在你的代码末尾添加以下写入逻辑（请替换为实际的数据变量名）：

{write_template}

记住：你的代码必须包含 open().write() 或 json.dump() 等写入操作！
"""
                # 找到最后一个 user 消息并追加，或者添加新的 user 消息
                messages.append({"role": "user", "content": strong_feedback})
            
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
            except (KeyError, IndexError) as e:
                error_msg = f"❌ 解析 LLM 响应失败: {result}"
                if self.logger:
                    self.logger.error(error_msg)
                return error_msg
            
            # 提取代码
            code = self.code_parser.extract_code(assistant_reply)
            
            if code:
                # 清理代码，移除残留的 markdown 标记
                code = self.code_parser.clean_code(code)
                
                # 如果出现 Bash，强制纠正
                if code.startswith("__BASH__:"):
                    if self.logger:
                        self.logger.warning("⚠️ 数据处理任务中检测到 Bash，强制纠正")
                    force_msg = "⚠️ 数据处理任务必须使用 Python，不要用 Bash。请重新生成 Python 代码。"
                    messages.append({"role": "assistant", "content": assistant_reply})
                    messages.append({"role": "user", "content": force_msg})
                    continue
                
                # 🔥 执行前：检查是否有写入操作
                has_write = self._has_write_operation(code)
                if not has_write:
                    write_target = self._detect_write_target(code)
                    if self.logger:
                        self.logger.warning(f"⚠️ 代码中未检测到写入操作")
                    
                    # 如果是第一次无写入，给出温和提示
                    if no_write_warning_count < 2:
                        no_write_warning_count += 1
                        write_template = self._build_write_template(user_input)
                        feedback = f"""⚠️ 你的代码中没有检测到文件写入操作。

数据处理任务必须将结果保存到文件，请添加写入逻辑。

参考模板：
{write_template}

请修改代码后重试。"""
                        messages.append({"role": "assistant", "content": assistant_reply})
                        messages.append({"role": "user", "content": feedback})
                        continue
                    else:
                        # 多次无写入，直接返回失败，避免无限循环
                        no_write_warning_count += 1
                        error_msg = f"""❌ 多次尝试均未生成包含写入操作的代码。

检测结果：代码中没有 open().write()、json.dump()、to_json() 等写入操作。

请人工检查以下内容：
1. 你的任务需求是否明确要求写入文件？
2. 生成的代码是否完整？
3. 是否在代码中使用了正确的写入方法？

最后一次生成的代码片段：
{code[:500]}...
"""
                        if self.logger:
                            self.logger.error(error_msg)
                        return error_msg
                
                # 执行前语法检查
                is_valid, syntax_error = self._validate_syntax(code)
                if not is_valid:
                    if self.logger:
                        self.logger.error(f"❌ 语法检查失败:\n{syntax_error}")
                    last_code = code
                    last_error = syntax_error
                    messages.append({"role": "assistant", "content": assistant_reply})
                    error_feedback = f"""代码存在语法错误，请修复后重试：

{syntax_error}

提示：请仔细检查括号、引号、冒号是否匹配，确保所有代码块完整闭合。"""
                    messages.append({"role": "user", "content": error_feedback})
                    continue
                
                # 执行 Python 代码
                if self.logger:
                    self.logger.info("🔧 检测到 Python 代码，开始执行...")
                
                expected_outputs = self.code_parser.extract_expected_outputs(code, user_input)
                success, output, new_files = self.code_executor.execute_python_code(code, expected_outputs)
                
                if success:
                    if self.logger:
                        self.logger.info(f"✅ 执行成功！\n{output[:500]}...")
                    
                    # 🔥 检查输出中是否有"未检测到写入操作"的警告
                    if "未检测到任何文件写入操作" in output or "警告" in output and "写入" in output:
                        if self.logger:
                            self.logger.warning("⚠️ CodeExecutor 报告未检测到写入操作")
                        # 即使执行成功，如果没有写入操作，也要继续迭代
                        no_write_warning_count += 1
                        write_template = self._build_write_template(user_input)
                        feedback = f"""代码执行成功，但 CodeExecutor 检测到没有文件写入操作。

请在你的代码末尾添加以下写入逻辑：

{write_template}

请修改代码后重试。"""
                        messages.append({"role": "assistant", "content": assistant_reply})
                        messages.append({"role": "user", "content": feedback})
                        continue
                    
                    # 检查是否有文件生成
                    if not new_files:
                        # 检查代码中是否有写入操作（可能写入到了已存在的文件）
                        if has_write:
                            if self.logger:
                                self.logger.info("ℹ️ 代码包含写入操作，但未检测到新文件（可能覆盖了已有文件）")
                            # 继续检查结果是否满意
                        else:
                            if self.logger:
                                self.logger.warning("⚠️ 代码执行成功但没有生成任何新文件")
                            no_write_warning_count += 1
                            write_template = self._build_write_template(user_input)
                            feedback = f"""⚠️ 代码执行成功但没有生成任何新文件。

请确保代码实际写入文件，并且写入路径正确。

参考模板：
{write_template}

请修改代码后重试。"""
                            messages.append({"role": "assistant", "content": assistant_reply})
                            messages.append({"role": "user", "content": feedback})
                            continue
                    
                    # 保存工具（如果包含函数或类定义）
                    if "def " in code or "class " in code:
                        device_name_for_save = self._detect_device(user_input)
                        saved_tool_path = self.tool_saver.save_tool(
                            code, device_name_for_save, user_input=user_input
                        )
                        if self.logger and saved_tool_path:
                            self.logger.info(f"✅ 工具已保存: {saved_tool_path}")
                    
                    # 检查结果是否满意
                    is_satisfied, reason = self.result_validator.check_output_satisfied(
                        output, new_files, code
                    )
                    
                    if is_satisfied:
                        if self.logger:
                            self.logger.info(f"✅ 任务满意: {reason}")
                        self.context_manager.add_assistant_message(f"任务完成，{reason}")
                        result_msg = "✅ 任务完成！"
                        if saved_tool_path:
                            result_msg += f"\n📁 工具已保存至: {saved_tool_path}"
                        if new_files:
                            result_msg += f"\n📁 生成的文件: {', '.join(new_files[:10])}"
                        result_msg += f"\n\n{output[:2000]}"
                        return result_msg
                    else:
                        if self.logger:
                            self.logger.info(f"📊 需要优化: {reason}")
                        last_code = code
                        last_error = f"执行结果不满意: {reason}"
                        messages.append({"role": "assistant", "content": assistant_reply})
                        messages.append({"role": "user", "content": f"执行成功，但需要优化。原因：{reason}\n\n请修改代码，确保生成正确的输出文件并提供详细的统计信息。"})
                else:
                    if self.logger:
                        self.logger.error(f"❌ 执行失败:\n{output}")
                    last_code = code
                    last_error = output
                    messages.append({"role": "assistant", "content": assistant_reply})
                    # 提供更详细的错误信息，帮助 LLM 修复
                    error_feedback = f"""代码执行失败，错误信息：
{output}

请修复代码后重试。注意检查：
1. 文件路径是否正确（使用相对路径，基于项目根目录）
2. 数据格式是否正确（JSONL 格式是否正确）
3. 是否有语法错误（括号、引号、冒号是否匹配）
4. 读取的文件是否存在
5. 数据加载后是否为空（打印 len(data) 确认）
6. 是否包含了正确的写入操作（open().write() 或 json.dump()）"""
                    messages.append({"role": "user", "content": error_feedback})
            else:
                # 没有代码块
                if self.logger:
                    self.logger.info("📝 无代码生成")
                force_msg = """
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ 没有检测到代码                                         ║
╠══════════════════════════════════════════════════════════════╣
║  请重新生成，用 ```python 代码块包裹完整的 Python 代码      ║
║  必须包含：读取 → 处理 → 写入 → 打印统计                   ║
╚══════════════════════════════════════════════════════════════╝
"""
                messages.append({"role": "assistant", "content": assistant_reply})
                messages.append({"role": "user", "content": force_msg})
                continue
        
        # 超过迭代次数
        return f"⚠️ 超过优化循环上限（{max_iterations}次），请人工介入。\n最后错误：{last_error}\n已生成文件：{saved_tool_path if saved_tool_path else '无'}"
    
    def _is_data_processing_task(self, text: str) -> bool:
        """判断是否是数据处理任务"""
        keywords = [
            "清洗", "聚合", "分析", "创建工具", "处理", "转换",
            "clean", "aggregate", "analyze", "process", "transform",
            "jsonl", "json", "传感器", "sensor", "可穿戴", "wearable"
        ]
        return any(kw in text.lower() for kw in keywords)
    
    def _detect_device(self, user_input: str) -> str:
        """从用户输入中检测设备名称"""
        if "wearos" in user_input.lower():
            return "wearos_1"
        # 可以扩展更多设备检测逻辑
        return "common"