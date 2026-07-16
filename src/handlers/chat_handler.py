"""
闲聊处理器
负责：处理闲聊对话
"""
from typing import List, Dict


class ChatHandler:
    """闲聊处理器"""
    
    def __init__(self, llm_client, context_manager, text_cleaner):
        """
        初始化闲聊处理器
        
        Args:
            llm_client: LLM客户端实例
            context_manager: 上下文管理器实例
            text_cleaner: 文本清理器实例
        """
        self.llm_client = llm_client
        self.context_manager = context_manager
        self.text_cleaner = text_cleaner
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def handle(self, user_input: str) -> str:
        """
        处理闲聊
        
        Args:
            user_input: 用户输入
            
        Returns:
            助手回复
        """
        if self.logger:
            self.logger.info("💬 闲聊模式")
        
        # 清理输入
        cleaned_input = self.text_cleaner.clean_text(user_input)
        cleaned_input = self.text_cleaner.truncate_large_input(cleaned_input, max_chars=8000)
        
        # 添加到对话历史
        self.context_manager.add_user_message(cleaned_input)
        
        # 检查是否需要压缩上下文
        if self.context_manager.should_compress():
            self.context_manager.compress_context(self.llm_client)
        
        # 构建消息
        messages = [
            {"role": "system", "content": "你是一个助手，可以回答问题。"},
        ] + self.context_manager.get_history()
        
        # 调用LLM
        result = self.llm_client.call_llm(messages, temperature=0.1)
        
        if "error" in result:
            error_msg = f"❌ LLM 调用失败: {result['error']}"
            if self.logger:
                self.logger.error(error_msg)
            return error_msg
        
        try:
            reply = result["choices"][0]["message"]["content"]
            reply = self.text_cleaner.clean_text(reply)
            self.context_manager.add_assistant_message(reply)
            return reply
        except (KeyError, IndexError) as e:
            error_msg = f"❌ 解析 LLM 响应失败: {result}"
            if self.logger:
                self.logger.error(error_msg)
            return error_msg