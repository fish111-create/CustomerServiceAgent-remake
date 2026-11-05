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


# ================= 4. 通用 LLM 配置 =================   
# LLM API 密钥（必需）
# 从环境变量获取，不允许硬编码在代码中
# 如果未设置，抛出明确的错误提示，避免服务在无效状态下启动
LLM_API_KEY: str = os.getenv("LLM_API_KEY")   #故意不给默认值，缺了就是 None
if not LLM_API_KEY:
    error_msg = "LLM_API_KEY 未设置，请在 .env 文件中配置。"
    logger.error(error_msg)  #打一条 ERROR 日志
    raise ValueError(error_msg)  #抛出异常，阻止服务启动

# LLM 服务基础 URL
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.example.com/v1")  #提供默认值，避免服务启动时出错

# LLM 模型名称  
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "default-model")  #提供默认值，避免服务启动时出错

logger.info(f"通用LLM配置已经加载")
logger.debug(f"LLM 配置 - BASE_URL:{LLM_BASE_URL},MODEL_NAME:{LLM_MODEL_NAME}")

# ================= 5. RAG 配置 ================= 
# 用于千问 Embedding 模型的向量检索
DASHSCOPE_API_KEY:str = os.getenv("DASHSCOPE_API_KEY")  #可选配置，默认空字符串
if not DASHSCOPE_API_KEY:
    error_msg = "DASHSCOPE_API_KEY 未设置，请在 .env 文件中配置。"
    logger.error(error_msg)
    raise ValueError(error_msg)  #抛出异常，阻止服务启动

logger.info("RAG配置已加载")


# ================= 6. ERP 系统配置 =================
"""                                                           
ERP 系统集成配置（可选）
- 用于产品质保核验等业务场景
- 支持对接企业真实 ERP 系统
- 如果未配置，系统将自动降级为本地 SN 码规则模拟
- 使用 Optional 类型提示，明确表示这些配置是可选的
"""             
ERP_API_URL: Optional[str] = os.getenv("ERP_API_URL")
ERP_API_KEY: Optional[str] = os.getenv("ERP_API_KEY")

# ================= 7. 启动配置摘要 ================= 
"""                                                            
启动时打印配置摘要
- 使用标准化的日志格式，替代原有的 emoji 表情
- 仅显示配置状态，不暴露敏感信息（如完整密钥）
- 使用不同的日志级别（INFO/WARNING/ERROR）表示不同重要程度
- 便于运维人员快速了解系统状态
"""       
logger.info("="*36)
logger.info("系统配置加载完成")
logger.info("="*36)

# 服务和文件系统配置
logger.info(f"服务地址：{HOST}:{PORT}")
logger.info(f"数据库路径: {DATABASE_PATH}")
logger.info(f"上传目录： {UPLOAD_DIR}")
logger.info(f"="*36)

# 通用 LLM 配置状态
llm_status = "[OK]已配置" if LLM_API_KEY else "[FAIL]未配置"
logger.info(f"通用LLM配置状态: {llm_status}")
logger.info(f"LLM BASE URL: {LLM_BASE_URL}")
logger.info(f"LLM MODEL NAME: {LLM_MODEL_NAME}")
logger.info(f"="*36)

# RAG 配置状态 
rag_status = "[OK]已配置" if DASHSCOPE_API_KEY else "[FAIL]未配置"
logger.info(f"RAG配置状态: {rag_status}")
logger.info(f"="*36)

# ERP 配置状态
if ERP_API_URL:
    logger.info(f"ERP 接口地址：{ERP_API_URL}([ok]已配置)")
else:
    logger.warning("ERP 接口地址:[WARN]未配置，系统将使用本地 SN 码规则模拟。")

logger.info("="*36)


# ================= 配置验证总结 ================= 
required_configs = {
    "LLM_API_KEY": LLM_API_KEY,
    "DASHSCOPE_API_KEY": DASHSCOPE_API_KEY
}

missing_configs = [key for key, value in required_configs.items() if not value]  #列表推导式，筛出值为空的键

if missing_configs:
    logger.error(f"必须配置项缺少：{','.join(missing_configs)}")
    logger.error("系统启动失败：缺少必需的配置项") 
else:
    logger.info("所有必需配置项验证通过，系统可以正常启动")

# 配置加载完成标志，可用于其他模块的依赖检查
CONFIG_LOADED = True  #标记本模块已完整执行
logger.info("配置模块初始化完成")