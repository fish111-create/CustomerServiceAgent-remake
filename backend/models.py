"""                                                             
Pydantic 数据模型定义
架构优化：引入 Enum 强校验拦截大模型幻觉、对齐最新无状态 Router、规范分页元数据
"""        
from enum import Enum
from typing import List,Optional,Dict,Any
from pydantic import BaseModel,Field
from datetime import datetime  #生成默认时间戳


# 1. 核心枚举定义 (强校验，拦截大模型幻觉)   
class UrgencyLevel(str,Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class WarrantyStatus(str,Enum):   #质保状态
    IN_WARRANTY = "In_warranty"
    OUT_OF_WARRANTY = "out_of_warranty"
    UNKNOWN = "unknown"

class TicketStatus(str,Enum):     #工单状态                                
    PENDING = "未处理"             #值是中文：接口和数据库都按这个字面量走
    PROCESSING = "处理中"
    RESOLVED = "已解决"
    CLOSED = "已关闭"

class BusinessImpact(str,Enum):  #业务影响
    NORMAL = "Normal"
    DEGRADED = "degraded"
    CRITICAL = "critical"

# 2. 对话与多模态请求模型
class ChatHistoryItem(BaseModel):   #一条历史消息
    role:str = Field(...,pattern="^(user|assistant|system)$")  #角色
    content:str 

class ChatResponse(BaseModel):
    """对话接口返回模型 (对齐最新自动建档逻辑)"""
    reply :str = Field(...,description="给客户的自然语言回复")  #LLM 回复
    ticket_created:bool = Field(...,description="是否自动创建了工单")  #是否创建工单
    ticket_id:Optional[str] = Field(None,description="工单 ID，如果没有创建工单则为 None")  #工单 ID
    urgency_level:Optional[UrgencyLevel] = Field(None,description="工单紧急程度")  #紧急程度
    warranty_status:Optional[str] = Field(None,description="质保状态(In_Warranty/Out_of_Warranty/Unknown)")  #质保状态
    sn_code:Optional[str] = Field(None,description="SN 码")  #SN 码
    ocr_text:Optional[str] = Field(None,description="OCR 识别的文本内容")  #OCR 文本




