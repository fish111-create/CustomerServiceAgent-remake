# 文件功能：提供客服工单与产品注册信息的 SQLite 存储及查询操作。
import sqlite3
import json
import os
import logging
from typing import List, Dict, Any,Optional
from datetime import datetime
from config import DATABASE_PATH
from contextlib import contextmanager   #把生成器变成 with 可用的上下文管理器

logger = logging.getLogger(__name__)

def _ensure_dir(path:str)->None: 
    dirname = os.path.dirname(path)               #去掉文件名，只留目录部分
    if dirname and not os.path.exists(dirname):   #目录非空且不存在才创建
        os.makedirs(dirname)

@contextmanager   
def get_db_connection():
    """
    使用上下文管理器确保数据库连接正确关闭。
    开启 WAL 模式与 busy_timeout，彻底解决 FastAPI 并发下的 "database is locked" 问题。
    """
    _ensure_dir(DATABASE_PATH)  #连接前先保证 data/ 存在
    # 增加 timeout 参数防止瞬间锁表 
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)  #设置超时为 10 秒
    conn.row_factory = sqlite3.Row  #结果可按列名取
    try:
        # 开启 WAL 模式，允许并发读写
        conn.execute("PRAGMA journal_mode=WAL;")
        # 设置 busy_timeout，避免瞬间锁表导致的 "database is locked" 错误
        conn.execute("PRAGMA busy_timeout=5000;")  # 5 秒
        yield conn   #交出连接，with 结束时回到这里继续
    finally:
        conn.close()

def init_db()->None:
    """初始化数据库表结构及索引"""
    try:
        with get_db_connection() as conn:   #借连接，退出自动关闭
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets ( 
                    id INTEGER PRIMARY KEY AUTOINCREMENT,  
                    ticket_id TEXT UNIQUE NOT NULL,         
                    raw_json TEXT NOT NULL,  
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT '未处理'            
                )
                ''')
            # 工单号序列表：按天记录当前最大序号，确保 CS-YYYYMMDD-NNNN 每天从 0001 递增
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ticket_sequences
                (
                    date_str TEXT PRIMARY KEY,       
                    seq INTEGER NOT NULL DEFAULT 0  
                )
                ''')
            # 产品注册表：SN 码 / 订单号 → 产品信息映射，支持智能体查询
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS product_registry
                (
                    sn_code TEXT PRIMARY KEY,    
                    order_id TEXT,
                    model_number TEXT NOT NULL,  
                    batch_code TEXT,             
                    production_year INTEGER,     
                    production_month INTEGER,   
                    product_name TEXT   
                )
                ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reg_order ON product_registry(order_id)')   
            # 兼容旧表：动态添加 status 列
            cursor.execute("PRAGMA table_info(tickets)")    #读出当前表的所有列
            columns = [col[1] for col in cursor.fetchall()] #col[1] 是列名，拼成列表
            if 'status' not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN status TEXT DEFAULT '未处理'")
                logger.info("[INFO]已经为tickets表格动态添加status列")

            # 建立索引加速查询 
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticket_id ON tickets(ticket_id)')   #按工单号查
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON tickets(created_at DESC)') #按时间倒序
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON tickets(status)')   #按状态筛

            conn.commit()
            logger.info("[INFO] 数据库初始化完成 (含 WAL 模式、ticket_sequences 序号列表、product_registry 产品注册表、status 列及索引)")
    except sqlite3.Error as e:
        logger.error(f"[ERROR]数据库初始化失败：{e}")
        raise


def save_ticket(ticket:Dict[str,Any])->None:
    """保存或更新工单 (UPSERT)"""
    ticket_id = ticket.get("ticket_id")
    if not ticket_id:
        raise ValueError("[ERROR]ticket_id 不能为空")

    raw_json = json.dumps(ticket,ensure_ascii=False) # 转 JSON，中文不转义
    created_at = ticket.get("created_at",datetime.now().isoformat())  #没有就取当前时间
    status = ticket.get("status","未处理")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''     
                    INSERT INTO tickets(ticket_id,raw_json,created_at,status)
                    VALUES(?,?,?,?) ON CONFLICT(ticket_id) DO   
                    UPDATE SET
                        raw_json = excluded.raw_json,    
                        status = excluded.status

            ''', (ticket_id, raw_json, created_at, status))
            conn.commit()
            logger.info(f"[INFO] 工单 {ticket_id} 已保存，状态: {status}")
    except sqlite3.Error as e:
        logger.error(f"[ERROR] 保存工单 {ticket_id} 失败: {e}")
        raise

def update_ticket_status(ticket_id:str,new_status:str)->bool:    #改状态，返回是否改到
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tickets
                SET status = ?
                WHERE ticket_id = ?
            ''', (new_status, ticket_id)) 
            affected = cursor.rowcount    #受影响行数，0 表示工单不存在
            conn.commit()
            if affected:
                logger.info(f"[INFO]工单{ticket_id}状态已经更新为{new_status}")
            else:
                logger.warning(f"[WARN] 尝试更新不存在的工单: {ticket_id}")
            return affected>0
    except sqlite3.Error as e:
        logger.error(f"[ERROR] 更新工单状态失败 {ticket_id}: {e}")
        return False

def get_all_tickets(limit:int = 99999,offset:int = 0)->List[Dict[str,Any]]:   #列表查询
    """获取工单列表 (支持分页，默认按时间倒序)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT raw_json,created_at,status
                FROM tickets
                ORDER BY created_at DESC LIMIT ?
                OFFSET ?
            ''',(limit,offset))
            rows = cursor.fetchall()   #取全部结果
            tickets = []

            for row in rows:
                try:
                    ticket = json.loads(row["raw_json"])
                    if"created_at" not in ticket:
                        ticket["created_at"] =  row["created_at"]
                        # 以数据库中的状态为准，覆盖 JSON 中可能不一致的状态
                    ticket["status"] = row["status"]
                    tickets.append(ticket)
                except json.JSONDecodeError as e:
                    logger.info(f"[WARN] 解析工单JSON失败，跳过，错误:{e}")
                    continue
            return tickets
    except sqlite3.Error as e:
        logger.error(f"[ERROR]获取工单列表失败：{e}")
        return  []

def get_tickets_by_urgency(urgency_level:str)->List[Dict[str,Any]]:
    """
    【性能优化】按紧急度过滤工单。
    使用 SQLite 的 json_extract 将过滤条件下推到数据库层，避免全表加载到 Python 内存。
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 直接从 JSON 字段中提取 urgency_level 进行 SQL 层面比对
            query = '''
                    SELECT raw_json,created_at,status
                    FROM tickets
                    WHERE json_extract(raw_json,'$.agent_business_assessment.urgency_level') = ?
                    ORDER BY created_at DESC\
                    '''
            cursor.execute(query,(urgency_level,))
            rows = cursor.fetchall()
            tickets = []

            for row in rows:
                try:
                    ticket = json.loads(row["raw_json"])
                    ticket["status"] = row["status"]
                    tickets.append(ticket)
                except json.JSONDecodeError:
                    continue
            return tickets
    except sqlite3.Error as e:
        logger.error(f"[ERROR] 按紧急度查询工单失败: {e}")
        return []

def get_ticket_by_id(ticket_id:str)->Optional[Dict[str,Any]]:
    """根据 ID 获取单个工单详情"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT raw_json,status FROM tickets WHERE ticket_id=?',(ticket_id,))
            row = cursor.fetchone()
            if row:
                ticket = json.loads(row["raw_json"])
                ticket["status"]=row["status"]
                return ticket
            return None
    except (sqlite3.Error,json.JSONDecodeError) as e:
        logger.error(f"[ERROR]获取工单详情失败{ticket_id}:{e}")
        return None

def get_tickets_count()->int:
    """获取工单总数"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM tickets') #COUNT 只返回一行一列
            return cursor.fetchone()[0]
    except sqlite3.Error as e:
        logger.error(f"[ERROR]获取工单总数失败:{e}")
        return 0

def generate_ticket_id()->str:
    """
    生成符合赛事要求的工单号：CS-YYYYMMDD-NNNN
    - NNNN 为当天从 0001 开始递增的序号
    - 使用原子 UPSERT 保证线程安全
    """
    date_str = datetime.now().strftime("%Y%m%d")   #当天日期
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 原子递增：插入或更新当日序号 
            cursor.execute('''
                INSERT INTO ticket_sequences(date_str,seq) VALUES(?,1)
                ON CONFLICT(date_str) DO UPDATE SET seq = seq+1

            ''',(date_str,))
            conn.commit()
            # 重新读出递增后的值
            cursor.execute('SELECT seq FROM ticket_sequences WHERE date_str=?',(date_str,))
            row = cursor.fetchone()
            seq = row["seq"] if row else 1
            ticket_id = f"CS-{date_str}-{seq:04d}"
            logger.info(f"[INFO]生成工单号:{ticket_id}")
            return ticket_id
    except sqlite3.Error as e:
        logger.error(f"[ERROR]生成工单号失败:{e}")
        # 降级：使用时间戳保证唯一性 
        fallback = f"CS-{date_str}-{int(datetime.now().timestamp() * 1000) % 10000:04d}"
        logger.warning(f"[WARN] 使用降级工单号: {fallback}")
        return fallback




        

