"""
数据处理 Agent 主程序 - 命令行交互式对话
使用拆分后的组件：llm_client, code_executor, context_manager, 
tool_scanner, tool_saver, task_classifier, handlers
"""
import sys
import logging
from pathlib import Path
from datetime import datetime

# 将项目根目录添加到 sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.settings import TOOLS_DIR, LOGS_DIR, LOG_ENABLED, LOG_LEVEL, MAX_PROCESSING_ITERATIONS
from src.prompt_loader import load_prompt, load_context_compression_config

# 导入所有组件
from src.core.llm_client import LLMClient
from src.core.code_executor import CodeExecutor
from src.core.context_manager import ContextManager
from src.core.tool_scanner import ToolScanner
from src.core.tool_saver import ToolSaver
from src.handlers.chat_handler import ChatHandler
from src.handlers.exploration_handler import ExplorationHandler
from src.handlers.processing_handler import ProcessingHandler
from src.utils.text_cleaner import TextCleaner
from src.utils.code_parser import CodeParser
from src.utils.result_validator import ResultValidator


class AgentRunner:
    """数据处理 Agent 运行器 - 命令行交互式对话"""
    
    def __init__(self):
        """初始化 Agent"""
        # 加载配置
        self.system_prompt = load_prompt("system_prompt.txt")
        self.context_config = load_context_compression_config()
        
        # 设置日志
        self.logger = self._setup_logger()
        
        # 初始化所有组件（按依赖顺序）
        self._init_components()
        
        # 扫描工具
        self.tool_scanner.scan()
        
        self.logger.info("=" * 60)
        self.logger.info("🤖 Agent 初始化完成")
        self.logger.info(f"   模型: {self.llm_client.get_model_name()}")
        self.logger.info(f"   工具目录: {TOOLS_DIR}")
        self.logger.info(f"   可用工具数: {self.tool_scanner.get_tool_count()}")
        self.logger.info("=" * 60)
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志：同时输出到命令行和文件"""
        logger = logging.getLogger("AgentRunner")
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        
        # 避免重复添加 handler
        if logger.handlers:
            return logger
        
        # 格式
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 命令行 handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)
        
        # 文件 handler
        if LOG_ENABLED:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            log_file = LOGS_DIR / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(f"📁 日志文件: {log_file}")
        
        return logger
    
    def _init_components(self):
        """初始化所有组件"""
        # 1. Utils（无依赖）
        self.text_cleaner = TextCleaner()
        self.code_parser = CodeParser()
        self.result_validator = ResultValidator()
        
        # 2. Core 组件（相互独立）
        self.llm_client = LLMClient()
        self.llm_client.set_logger(self.logger)
        
        self.code_executor = CodeExecutor()
        self.code_executor.set_logger(self.logger)
        
        self.context_manager = ContextManager(self.context_config)
        self.context_manager.set_logger(self.logger)
        
        self.tool_scanner = ToolScanner()
        self.tool_scanner.set_logger(self.logger)
        
        self.tool_saver = ToolSaver()
        self.tool_saver.set_logger(self.logger)
        
        # 3. Handlers
        self.chat_handler = ChatHandler(
            self.llm_client, self.context_manager, self.text_cleaner
        )
        self.chat_handler.set_logger(self.logger)
        
        self.exploration_handler = ExplorationHandler(
            self.llm_client, self.code_executor, self.context_manager,
            self.tool_scanner, self.text_cleaner, self.code_parser
        )
        self.exploration_handler.set_logger(self.logger)
        
        self.processing_handler = ProcessingHandler(
            self.llm_client, self.code_executor, self.context_manager,
            self.tool_scanner, self.tool_saver, self.text_cleaner,
            self.code_parser, self.result_validator
        )
        self.processing_handler.set_logger(self.logger)
        self.processing_handler.set_system_prompt(self.system_prompt)
    
    def _get_tools_description(self) -> str:
        """生成工具列表描述"""
        return self.tool_scanner.get_description()
    
    def _classify_with_llm(self, user_input: str) -> str:
        """
        使用 LLM 判断用户意图
        
        Returns:
            'processing': 数据处理任务
            'exploration': 探索类任务
            'chat': 闲聊
        """
        # 构建分类提示
        messages = [
            {"role": "system", "content": """你是一个任务分类器。根据用户输入，判断用户想要做什么。

请只输出以下三种类型之一：
- processing: 用户想要处理、分析、转换数据，或者要求生成代码、创建工具
- exploration: 用户想要查看、列出、浏览、检查文件或目录
- chat: 用户想要闲聊、提问、打招呼

只输出类型名称，不要输出其他内容。"""},
            {"role": "user", "content": user_input}
        ]
        
        result = self.llm_client.call_llm(messages, temperature=0, max_tokens=20)
        
        if "error" in result:
            self.logger.warning(f"LLM 分类失败，默认使用 processing: {result['error']}")
            return "processing"
        
        try:
            reply = result["choices"][0]["message"]["content"].strip().lower()
            self.logger.info(f"📊 LLM 分类结果: {reply}")
            
            if "exploration" in reply:
                return "exploration"
            elif "chat" in reply:
                return "chat"
            else:
                return "processing"
        except (KeyError, IndexError):
            self.logger.warning("解析 LLM 分类结果失败，默认使用 processing")
            return "processing"
    
    def _process_task(self, user_input: str, max_iterations: int = MAX_PROCESSING_ITERATIONS) -> str:
        """
        处理用户任务 - 先让 LLM 判断意图，再分发给对应 handler
        
        Args:
            user_input: 用户输入
            max_iterations: 最大迭代次数（仅对处理任务有效）
            
        Returns:
            处理结果
        """
        # 清理输入
        cleaned_input = self.text_cleaner.clean_text(user_input)
        cleaned_input = self.text_cleaner.truncate_large_input(cleaned_input, max_chars=8000)
        
        # 让 LLM 判断意图
        task_type = self._classify_with_llm(cleaned_input)
        
        if task_type == "processing":
            return self.processing_handler.handle(cleaned_input, max_iterations)
        elif task_type == "exploration":
            return self.exploration_handler.handle(cleaned_input)
        else:
            return self.chat_handler.handle(cleaned_input)
    
    def run(self):
        """启动交互式对话"""
        print("\n" + "=" * 60)
        print("🤖 数据处理 Agent 已启动")
        print("=" * 60)
        print(f"📁 工具目录: {TOOLS_DIR}")
        print(f"📦 可用工具数: {self.tool_scanner.get_tool_count()}")
        print("\n💡 输入 'exit' 或 'quit' 退出")
        print("💡 输入 'tools' 查看可用工具列表")
        print("💡 输入 'status' 查看对话状态")
        print("=" * 60 + "\n")
        
        while True:
            try:
                user_input = input("你 > ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("👋 再见！")
                    break
                
                if user_input.lower() == 'tools':
                    print(self._get_tools_description())
                    continue
                
                if user_input.lower() == 'status':
                    print(f"对话轮次: {self.context_manager.get_turns()}")
                    print(f"工具数量: {self.tool_scanner.get_tool_count()}")
                    continue
                
                response = self._process_task(user_input)
                print(f"\n🤖 Agent > {response}\n")
                
            except KeyboardInterrupt:
                print("\n\n👋 检测到中断，再见！")
                break
            except Exception as e:
                self.logger.error(f"❌ 运行时错误: {e}")
                print(f"\n❌ 错误: {e}\n")


def main():
    """入口函数"""
    runner = AgentRunner()
    runner.run()


if __name__ == "__main__":
    main()