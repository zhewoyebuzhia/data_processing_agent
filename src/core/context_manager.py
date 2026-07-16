"""
上下文管理器
负责：对话历史管理、上下文压缩
"""
from typing import List, Dict, Any


class ContextManager:
    """对话上下文管理器"""
    
    def __init__(self, context_config: Dict[str, Any]):
        """
        初始化上下文管理器
        
        Args:
            context_config: 上下文压缩配置
        """
        self.conversation_history: List[Dict[str, str]] = []
        self.total_turns = 0
        self.context_config = context_config
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.conversation_history.append({"role": "user", "content": content})
        self.total_turns += 1
    
    def add_assistant_message(self, content: str) -> None:
        """添加助手消息"""
        self.conversation_history.append({"role": "assistant", "content": content})
        self.total_turns += 1
    
    def get_history(self) -> List[Dict[str, str]]:
        """获取完整对话历史"""
        return self.conversation_history
    
    def get_turns(self) -> int:
        """获取对话轮次"""
        return self.total_turns
    
    def should_compress(self) -> bool:
        """
        判断是否需要触发上下文压缩
        
        Returns:
            是否需要压缩
        """
        if not self.context_config.get("enabled", True):
            return False
        max_turns = self.context_config.get("config", {}).get("max_turns_before_compression", 20)
        return self.total_turns >= max_turns
    
    def compress_context(self, llm_client) -> None:
        """
        压缩对话上下文
        
        Args:
            llm_client: LLM客户端实例，用于生成摘要
        """
        if self.logger:
            self.logger.info("🔄 触发上下文压缩...")
        
        config = self.context_config.get("config", {})
        keep_recent = config.get("keep_recent_turns", 10)
        summary_prompt_template = config.get("summary_prompt", "")
        
        if len(self.conversation_history) <= keep_recent:
            if self.logger:
                self.logger.debug("对话历史太短，跳过压缩")
            return
        
        # 分割历史：要压缩的部分 + 保留的最近对话
        history_to_compress = self.conversation_history[:-keep_recent]
        recent_history = self.conversation_history[-keep_recent:]
        
        # 构建摘要提示
        history_text = "\n".join([
            f"{msg['role']}: {msg['content'][:500]}..." 
            for msg in history_to_compress
        ])
        
        summary_prompt = summary_prompt_template.format(history=history_text)
        
        # 调用LLM生成摘要
        messages = [
            {"role": "system", "content": "你是一个对话摘要助手，请按要求压缩对话历史。"},
            {"role": "user", "content": summary_prompt}
        ]
        
        result = llm_client.call_llm(messages, temperature=0.3, max_tokens=512)
        
        if "error" in result:
            if self.logger:
                self.logger.warning("⚠️ 上下文压缩失败，跳过")
            return
        
        try:
            summary = result["choices"][0]["message"]["content"]
            # 重建历史：摘要 + 最近对话
            self.conversation_history = [
                {"role": "system", "content": f"[对话摘要] {summary}"}
            ] + recent_history
            self.total_turns = len(self.conversation_history)
            if self.logger:
                self.logger.info("✅ 上下文压缩完成")
        except (KeyError, IndexError) as e:
            if self.logger:
                self.logger.warning(f"⚠️ 解析压缩摘要失败: {e}")
    
    def clear_history(self) -> None:
        """清空对话历史"""
        self.conversation_history = []
        self.total_turns = 0
        if self.logger:
            self.logger.info("对话历史已清空")