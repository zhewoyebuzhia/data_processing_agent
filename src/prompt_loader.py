import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.settings import PROMPTS_DIR


def load_prompt(filename: str) -> str:
    """加载纯文本提示词文件"""
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"提示词文件不存在: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_context_compression_config():
    """加载上下文压缩配置"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "context_compression", 
            PROMPTS_DIR / "context_compression.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {
            "enabled": getattr(module, "ENABLE_CONTEXT_COMPRESSION", True),
            "config": getattr(module, "COMPRESSION_CONFIG", {})
        }
    except Exception as e:
        print(f"警告：加载上下文压缩配置失败: {e}")
        return {"enabled": False, "config": {}}