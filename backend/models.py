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

# 3. 工单内部数据结构 (严格约束) 
class ExtractedData(BaseModel):
    """从多模态/文本中提取的结构化数据"""
    order_id:Optional[str] = None
    model_number:Optional[str] = None
    batch_code:Optional[str] = None
    sn_code:Optional[str]  = Field(None,description="设备序列号，用于质保核验")
    evidence_images:Optional[List[str]] = Field(default_factory=list,description="证据图片的 URL 列表")  #用 factory 避免可变默认值共享
    ocr_text:Optional[str] = Field(None,description="OCR 识别的文本内容")  #OCR 文本

class AgentBusinessAssessment(BaseModel):
    """智能体对业务场景的分析结果"""
    issue_category:str = Field(...,description="问题分类")  #问题分类(必填)
    business_impact:BusinessImpact = Field(BusinessImpact.NORMAL,description="业务影响")  #业务影响(必填,有默认值)
    urgency_level:UrgencyLevel = Field(...,description="紧急程度")  #紧急程度(必填)
    warranty_status:WarrantyStatus = Field(WarrantyStatus.UNKNOWN,description="质保状态")  #质保状态(必填,默认UNKNOWN)

class Ticket(BaseModel):
    """标准工单模型 (对应数据库存储结构)"""
    ticket_id:str = Field(...,description="工单唯一标识")
    created_at:str = Field(default_factory=lambda: datetime.now().isoformat())  #不传就自动生成当前时间
    extracted_data:ExtractedData 
    agent_business_assessment:AgentBusinessAssessment
    routing_decision:str = Field(...,description="路由决策结果")  #路由决策结果
    auto_reply_sent:str = Field(...,description="给用户发送的完整回复")  #是否已发送自动回复
    status:TicketStatus = Field(TicketStatus.PENDING,description="工单状态")  #工单状态，默认未处理

# 4. 列表查询与分页响应
class TicketListResponse(BaseModel):
    """工单列表分页响应"""
    tickets:List[Ticket]
    total:int = Field(...,description="符合条件总工单数")  #总工单数
    limit:int = Field(...,description="当前页大小")
    offset:int = Field(...,description="当前页偏移量")  

class TicketUpdateRequest(BaseModel):   #更新状态的请求体
    """更新工单状态请求"""
    ticket_id:str
    new_status:TicketStatus             #用枚举限制只能传四个合法状态


