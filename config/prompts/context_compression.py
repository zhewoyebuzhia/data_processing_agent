# 上下文压缩策略配置

COMPRESSION_CONFIG = {
    # 当对话轮次超过此值时触发压缩
    "max_turns_before_compression": 20,
    
    # 压缩时保留的最近对话轮次数
    "keep_recent_turns": 10,
    
    # 压缩时生成摘要的提示词模板
    "summary_prompt": """请对以下对话历史进行压缩摘要，保留以下关键信息：
1. 用户的核心需求
2. 已有的工具清单及其功能
3. 已处理的数据集和结果
4. 待解决的问题或后续计划

对话历史：
{history}

请输出一份结构化的摘要，保留所有关键细节。"""
}

# 是否启用压缩
ENABLE_CONTEXT_COMPRESSION = True