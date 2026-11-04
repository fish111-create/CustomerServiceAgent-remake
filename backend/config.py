"""
全局配置模块 (Global Configuration)
====================================
本文件是整个后端服务的配置中心，集中管理所有环境变量和系统常量。

架构设计亮点：
1. 环境变量注入：通过 .env 文件管理敏感信息，避免密钥硬编码在代码中。
2. Optional 类型安全：对可选配置（如 ERP 接口）使用 Optional 类型提示，增强代码可读性。
3. 启动摘要脱敏打印：服务启动时在控制台打印配置状态，但不暴露真实密钥，方便运维排查。
4. 标准化日志输出：使用 logging 替代 print，移除所有 Emoji 表情，采用纯文本标签（如 [OK], [WARN]），
确保在各类服务器终端、Docker 日志收集系统中不会出现乱码。
5. 供应商中立设计：使用 LLM_ 前缀替代供应商特定前缀，支持多种大模型服务无缝切换。
"""
# ================= 导入依赖库 =================
import logging
import os 
from pathlib import Path #面向对象的路径操作
from typing import Optional #表示"这个值可以是 None"
from dotenv import load_dotenv #负责把 .env 读进环境变量


# ================= 日志系统初始化 ================= 
# 格式说明：[时间] [日志级别] [模块名] - 消息内容 
logging.basicConfig(  #调用 basicConfig，配置"根 logger"；多参数调用
    level = logging.INFO,  #全局最低级别。INFO 意味着 debug() 不输出
    format = "%(asctime)s [%(levelname)s][%(name)s]-%(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S" #指定上面 %(asctime)s 的日期格式
)

logger = logging.getLogger("Config")  # 取一个名叫 Config 的 logger 

# ================= 环境变量加载 ================= 
# 所有默认路径都以 backend 目录为基准
BASE_DIR = Path(__file__).resolve().parent  #算出 backend/ 的绝对路径

def _resolve_runtime_path(value:str)->str:
    path = Path(value).expanduser()  #把字符串转成 Path 对象，并展开 ~ 家目录
    if not path.is_absolute():  #不是绝对路径吗？
        path = BASE_DIR/path    #是相对路径 → 拼到 backend/ 后面
    return str(path.resolve())  #规范化成绝对路径，再转回字符串返回

# 显式加载 backend/.env，不依赖启动命令的当前目录。
load_dotenv(BASE_DIR/'.env')
logger.info("环境变量加载完成") 


# ================= 1. 服务基础配置 =================
HOST: str = os.getenv("HOST","0.0.0.0")  #取环境变量 HOST，没有就用 0.0.0.0
PORT: int = int(os.getenv("PORT",8000))  #同上，但结果强制转成整数
logger.debug(f"服务配置 - HOST:{HOST},PORT:{PORT}")  #调试日志



# ================= 2. 数据库配置 =================
# 使用相对路径 ./data/tickets.db，确保 data 目录存在
DATABASE_PATH: str = _resolve_runtime_path(os.getenv("DATABASE_PATH","data/tickets.db"))
logger.debug(f"数据库配置 - DATABASE_PATH:{DATABASE_PATH}")  #调试日志


# ================= 3. 文件上传配置 =================
# 文件上传目录路径
# 系统会自动创建该目录
UPLOAD_DIR: str = _resolve_runtime_path(os.getenv("UPLOAD_DIR","uploads"))
CHROMA_PERSIST_DIRECTORY: str = _resolve_runtime_path(
    os.getenv("CHROMA_PERSIST_DIRECTORY","data/chroma_db")  #读向量库目录
)
SOP_DIR: str = _resolve_runtime_path(os.getenv("SOP_DIR","data/sop")) #读 SOP 文件目录
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  #最大上传文件大小，默认 50MB

# 确保必要的目录存在，避免运行时错误
# exist_ok=True 参数确保目录已存在时不会抛出异常
os.makedirs(UPLOAD_DIR, exist_ok=True)  #建 uploads
os.makedirs(Path(DATABASE_PATH).parent, exist_ok=True)  #建 data/
os.makedirs(CHROMA_PERSIST_DIRECTORY, exist_ok=True)  #建 data/chroma_db
os.makedirs(SOP_DIR, exist_ok=True)  #建 data/sop
logger.info(f"文件系统初始化完成 - 上传目录:{UPLOAD_DIR}, 数据目录:{Path(DATABASE_PATH).parent}")  #启动日志