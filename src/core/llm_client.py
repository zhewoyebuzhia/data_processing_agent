"""
LLM客户端
负责：LLM API调用、重试、超时处理
"""
import json
import time
from typing import List, Dict, Optional, Any
import requests

from config.settings import API_BASE_URL, API_KEY, MODEL_CHAT
from src.utils.text_cleaner import TextCleaner


class LLMClient:
    """LLM API 客户端"""
    
    def __init__(self):
        """
        初始化LLM客户端
        """
        self.api_base_url = API_BASE_URL
        self.api_key = API_KEY
        self.model = MODEL_CHAT
        
        # API 重试配置
        self.timeout_base = 180  # 基础超时时间（秒）
        self.max_retries = 3     # 最大重试次数
        self.retry_backoff = 30  # 初始退避时间（秒）
        
        self.text_cleaner = TextCleaner()
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def call_llm(self, messages: List[Dict[str, str]], temperature: float = 0.1, 
                 max_tokens: int = None, attempt: int = 1) -> Dict:
        """
        调用 LLM API，支持指数退避重试
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成Token数，None则自动判断
            attempt: 当前尝试次数（内部使用）
            
        Returns:
            API响应字典，失败时返回 {"error": "错误信息"}
        """
        # 过滤所有消息内容中的坏字符
        cleaned_messages = []
        for msg in messages:
            cleaned_msg = {
                "role": msg["role"],
                "content": self.text_cleaner.clean_text(msg["content"]) if isinstance(msg["content"], str) else msg["content"]
            }
            cleaned_messages.append(cleaned_msg)
        
        # 自动判断 max_tokens
        if max_tokens is None:
            # 检查是否是代码生成任务
            is_code_task = any(
                "必须生成" in msg.get("content", "") or "代码" in msg.get("content", "")
                for msg in messages if msg.get("role") == "system"
            )
            max_tokens = 2048 if is_code_task else 1024
        
        # 估算Token数并警告
        estimated_tokens = self.text_cleaner.estimate_tokens(cleaned_messages)
        if estimated_tokens > 8000 and self.logger:
            self.logger.warning(f"⚠️ 请求Token数约 {estimated_tokens}，可能影响响应速度")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": cleaned_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        url = f"{self.api_base_url}/chat/completions"
        
        # 动态超时：随重试次数增加
        timeout = self.timeout_base + (attempt - 1) * 60  # 180s, 240s, 300s
        
        try:
            if self.logger:
                self.logger.debug(f"📤 API请求: max_tokens={max_tokens}, timeout={timeout}s, 尝试={attempt}")
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout as e:
            if attempt < self.max_retries:
                # 指数退避：2^attempt * backoff
                wait_time = (2 ** attempt) * self.retry_backoff
                if self.logger:
                    self.logger.warning(f"⏱️ 请求超时 (尝试 {attempt}/{self.max_retries})")
                    self.logger.warning(f"   等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                return self.call_llm(messages, temperature, max_tokens, attempt + 1)
            else:
                if self.logger:
                    self.logger.error(f"❌ 所有重试均超时 (尝试 {self.max_retries} 次)")
                return {"error": f"超时重试{self.max_retries}次后仍失败: {e}"}
                
        except requests.exceptions.RequestException as e:
            if self.logger:
                self.logger.error(f"❌ API 请求失败: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    self.logger.error(f"响应内容: {e.response.text}")
            return {"error": str(e)}
    
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        return self.model