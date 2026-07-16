import os
from dotenv import load_dotenv
from pathlib import Path

# 加载 .env 文件
load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# API 配置
API_BASE_URL = os.getenv("API_BASE_URL")
API_KEY = os.getenv("API_KEY")
MODEL_CHAT = os.getenv("MODEL_CHAT", "deepseek-chat")
MODEL_REASONER = os.getenv("MODEL_REASONER", "deepseek-reasoner")

# 路径配置
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_CLEANED_DIR = BASE_DIR / "data" / "cleaned"
DATA_AGGREGATED_DIR = BASE_DIR / "data" / "aggregated"
TOOLS_DIR = BASE_DIR / "tools"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "config" / "prompts"

# 确保必要的目录存在
for dir_path in [DATA_RAW_DIR, DATA_CLEANED_DIR, DATA_AGGREGATED_DIR, 
                 TOOLS_DIR, OUTPUTS_DIR, LOGS_DIR, PROMPTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 日志配置
LOG_ENABLED = True                      # 是否启用文件日志
LOG_LEVEL = "INFO"                      # DEBUG / INFO / WARNING / ERROR

# 处理任务配置
MAX_PROCESSING_ITERATIONS = int(os.getenv("MAX_PROCESSING_ITERATIONS", "10"))