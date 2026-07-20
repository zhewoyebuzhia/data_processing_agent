"""Handler for agent-generated, one-shot data collection tools."""
import ast
import re
from pathlib import Path
from typing import Optional

from config.settings import CODE_GENERATION_MAX_TOKENS


class CollectionHandler:
    """Generate, validate, save, and optionally schedule collection tools."""

    def __init__(self, llm_client, code_executor, context_manager, tool_scanner,
                 tool_saver, text_cleaner, code_parser, scheduler):
        self.llm_client = llm_client
        self.code_executor = code_executor
        self.context_manager = context_manager
        self.tool_scanner = tool_scanner
        self.tool_saver = tool_saver
        self.text_cleaner = text_cleaner
        self.code_parser = code_parser
        self.scheduler = scheduler
        self.logger = None

    def set_logger(self, logger):
        self.logger = logger

    @staticmethod
    def _detect_interval_seconds(text: str) -> Optional[int]:
        match = re.search(r"(?:每隔|每|间隔)\s*(\d+(?:\.\d+)?)\s*(秒|s|sec|seconds?|分钟|分|min|小时|时|hour|h)", text, re.I)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2).lower()
        multiplier = 3600 if unit in {"小时", "时", "hour", "h"} else 60 if unit in {"分钟", "分", "min"} else 1
        seconds = value * multiplier
        return int(seconds) if seconds.is_integer() else None

    @staticmethod
    def _detect_format(text: str) -> str:
        """Honor the format specified by the user; JSON is the default."""
        return "jsonl" if re.search(r"jsonl", text, re.I) else "json"

    @staticmethod
    def _detect_tool_device(text: str) -> Optional[str]:
        """Extract `tools/<device>/` without confusing it with an output path."""
        match = re.search(r"(?:保存到|保存在)\s*[`'\"]?(tools/[A-Za-z0-9_-]+/?)(?:\s*中)?", text, re.I)
        if not match:
            return None
        return Path(match.group(1)).name

    @staticmethod
    def _detect_output_path(text: str, device: str, data_format: str) -> str:
        """Only accept a project-local data/ path as a collection output target."""
        data_paths = re.findall(r"\bdata/[A-Za-z0-9_./-]+", text, re.I)
        raw_path = data_paths[-1] if data_paths else f"data/raw/{device}/"
        if raw_path.endswith(("/", "\\")):
            output_path = f"{raw_path.rstrip('/\\')}/collection"
        else:
            output_path = raw_path
        suffix = f".{data_format}"
        if not output_path.lower().endswith(suffix):
            output_path += suffix
        path = Path(output_path)
        if path.is_absolute() or ".." in path.parts:
            return f"data/raw/{device}/collection{suffix}"
        return str(path).replace("\\", "/")

    @staticmethod
    def _detect_device(text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ("电脑", "计算机", "笔记本", "computer", "laptop", "pc", "电池")):
            return "computer_status"
        if any(word in lowered for word in ("手表", "wearos", "watch")):
            return "wearable"
        if any(word in lowered for word in ("手机", "phone", "android", "ios")):
            return "mobile"
        if any(word in lowered for word in ("家具", "家居", "home", "iot")):
            return "smart_home"
        return "collection_source"

    def _messages(self, user_input: str, device: str, output_path: str, data_format: str):
        write_instruction = (
            "将每条记录作为一行 JSON 追加写入 .jsonl 文件。"
            if data_format == "jsonl" else
            "读取已有 JSON 数组（不存在时使用空数组）、追加一条记录、再原子性写回一个 .json 文件。"
        )
        return [
            {"role": "system", "content": """你负责创建可复用的数据采集 Python 工具。只输出一个完整的 ```python 代码块，不要解释。
工具每次运行只采集一次；禁止无限循环、sleep、创建后台进程或计划任务。调度由外部框架处理。
必须定义一个语义明确的 collect_* 函数和 main 入口；采集当前设备或用户指定数据源；每条记录必须带 ISO 8601 时间戳。
使用 pathlib.Path.cwd() 或已注入的 PROJECT_ROOT；不得使用绝对路径、__file__、subprocess、shell 命令、删除操作或访问项目目录外的路径。
处理数据源不可用、权限不足和字段缺失，失败时给出清晰错误。优先使用 Python 标准库；只用实际可访问的本机 API、已安装库、已配置网络 API 或用户提供的连接方式；不要伪造数据。"""},
            {"role": "system", "content": f"本次设备标识为 {device}。{write_instruction} 输出文件必须是项目内相对路径 {output_path}；请在代码中显式使用 Path(\"{output_path}\")。"},
            {"role": "system", "content": f"当前可用工具：\n{self.tool_scanner.get_description()}"},
            {"role": "user", "content": user_input},
        ]

    def handle(self, user_input: str) -> str:
        if self.logger:
            self.logger.info("📡 数据采集任务模式")
        cleaned = self.text_cleaner.truncate_large_input(self.text_cleaner.clean_text(user_input), 8000)
        self.context_manager.add_user_message(cleaned)
        device = self._detect_tool_device(cleaned) or self._detect_device(cleaned)
        interval = self._detect_interval_seconds(cleaned)
        data_format = self._detect_format(cleaned)
        output_path = self._detect_output_path(cleaned, device, data_format)
        messages = self._messages(cleaned, device, output_path, data_format)
        last_error = "未生成代码"

        for attempt in range(1, 4):
            if self.logger:
                self.logger.info("🔄 采集工具生成尝试 %s/3", attempt)
            result = self.llm_client.call_llm(messages, temperature=0.1, max_tokens=CODE_GENERATION_MAX_TOKENS)
            if "error" in result:
                return f"❌ LLM 调用失败: {result['error']}"
            try:
                choice = result["choices"][0]
                reply = self.text_cleaner.clean_text(choice["message"]["content"])
                if self.logger:
                    self.logger.info("📝 采集工具 LLM 回复：\n%s", reply[:2000])
            except (KeyError, IndexError) as exc:
                return f"❌ 解析 LLM 响应失败: {exc}"

            if choice.get("finish_reason") == "length":
                last_error = "生成内容被长度限制截断"
                messages = self._messages(cleaned, device, output_path, data_format) + [{"role": "user", "content": "请从头生成更精简但完整的代码；上一轮被截断。"}]
                continue

            code = self.code_parser.extract_code(reply)
            if not code:
                last_error = "未检测到完整 Python 代码块"
                messages = self._messages(cleaned, device, output_path, data_format) + [{"role": "user", "content": "请只输出一个完整、闭合的 Python 代码块。"}]
                continue
            code = self.code_parser.clean_code(code)
            try:
                ast.parse(code)
            except SyntaxError as exc:
                last_error = f"语法错误：{exc.msg}"
                messages = self._messages(cleaned, device, output_path, data_format) + [
                    {"role": "assistant", "content": reply[:6000]},
                    {"role": "user", "content": f"代码{last_error}，请修复后完整重发。"},
                ]
                continue
            if re.search(r"while\s+True\s*[:]|time\.sleep\s*\(", code):
                last_error = "代码包含循环或 sleep；调度应由 Worker 完成"
                messages = self._messages(cleaned, device, output_path, data_format) + [{"role": "user", "content": "工具只能采集一次，删除 while True 和 time.sleep；调度由 Worker 处理。请完整重发。"}]
                continue
            write_pattern = r"\.write\s*\(" if data_format == "jsonl" else r"json\.dump\s*\("
            if not re.search(write_pattern, code):
                last_error = f"代码没有 {data_format} 写入操作"
                write_feedback = "代码必须将单条记录追加写入 JSONL 文件" if data_format == "jsonl" else "代码必须读取、追加并 json.dump 写回合法 JSON 数组"
                messages = self._messages(cleaned, device, output_path, data_format) + [{"role": "user", "content": f"{write_feedback}，请完整重发。"}]
                continue
            if output_path not in code.replace("\\", "/"):
                last_error = f"代码未使用指定输出路径 {output_path}"
                messages = self._messages(cleaned, device, output_path, data_format) + [{"role": "user", "content": f"必须显式使用输出路径 {output_path}，请修正后完整重发。"}]
                continue

            success, output, new_files = self.code_executor.execute_python_code(code)
            if not success:
                last_error = output[:1500]
                messages = self._messages(cleaned, device, output_path, data_format) + [
                    {"role": "assistant", "content": reply[:6000]},
                    {"role": "user", "content": f"执行失败：{last_error}\n请修复并完整重发。"},
                ]
                continue

            if self.logger:
                self.logger.info("✅ 采集工具验证执行成功：\n%s", output[:2000])

            tool_path = self.tool_saver.save_tool(code, device, user_input=cleaned)
            self.tool_scanner.scan()
            if self.logger:
                self.logger.info("💾 已保存采集工具：%s", tool_path)
            lines = ["✅ 已生成并完成一次验证采集。", f"📁 工具：{tool_path}"]
            if new_files:
                lines.append(f"📦 本次数据：{', '.join(new_files[:5])}")
            if interval:
                scheduled, task = self.scheduler.register(tool_path, device, interval)
                if self.logger:
                    self.logger.info("⏱️ 采集调度结果：%s", task)
                lines.append(
                    f"⏱️ 已注册每 {interval} 秒运行一次的独立采集任务（Worker：{task}）"
                    if scheduled else f"⚠️ 工具已生成，但未能创建计划任务：{task}"
                )
            else:
                lines.append("ℹ️ 未检测到采集间隔；工具已就绪。请求中写“间隔 30s”或“每隔 5 分钟”即可注册独立采集任务。")
            self.context_manager.add_assistant_message("采集工具已生成")
            return "\n".join(lines) + f"\n\n{output[:1000]}"

        return f"❌ 采集工具生成失败，已尝试 3 次。最后错误：{last_error}"
