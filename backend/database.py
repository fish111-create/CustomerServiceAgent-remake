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
                    id INTEGER PRIMARY KEY AUTOINCREMENT   #自增主键，内部用
                    ticket_id TEXT UNIQUE NOT NULL         #业务工单号，唯一且非空
                    raw_json TEXT NOT NULL  
                    created_at TEXT NOT NULL
                    status TEXT DEFAULT '未处理'            #处理状态，默认未处理
                )
                ''')
            # 工单号序列表：按天记录当前最大序号，确保 CS-YYYYMMDD-NNNN 每天从 0001 递增
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ticket_sequences
                (
                    date_str TEXT PRIMARY KEY       #日期做主键，一天一行
                    seq INTEGER NOT NULL DEFAULT 0  #当天已用到的最大序号
                )
                ''')
            # 产品注册表：SN 码 / 订单号 → 产品信息映射，支持智能体查询
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS product_registry
                (
                    sn_code TEXT PRIMARY KEY    #SN 做主键，天然去重
                    order_id TEXT 
                    model_number TEXT NOT NULL  #型号，必填
                    batch_code TEXT             #批次
                    production_year INTEGER     #生产年
                    production_month INTEGER   
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
    except sqlite3.error as e:
        logger.error(f"[ERROR]数据库初始化失败：{e}")
        raise


def save_ticket(ticket:Dict[str,Any])->None:
    """保存或更新工单 (UPSERT)"""
    ticket_id = ticket.get("ticket_id")
    if not ticket_id:
        raise ValueError("[ERROR]ticket_id 不能为空")

    raw_json = json.dump(ticket,ensure_ascii=False) # 转 JSON，中文不转义
    created_at = ticket_id("create_at",datetime.now().isoformat())  #没有就取当前时间
    status = ticket.get("status","未处理")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''     #UPSERT 语句
                    INSERT INFO ticket(ticket_id,raw_json,create_at,status)
                    VALUE(?,?,?,?) ON CONFLICT(ticket_id) DO   #主键冲突时不报错，转更新

                    UODATE SET
                        raw_json = exclude.raw_json    #excluded 指"本次想插入的新值
                        status = exclude.status

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
                UPDATE ticket
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
                SELECT raw_json,created_at.status
                FROM tickets
                ORDER BY created_at DESC LIMIT ?
                OFFSET ?
            ''',(limit,offset))
            rows = cursor.fetchall()   #取全部结果
            tickets = []

            for row in rows:
                try:
                    ticket = json.loads(row["raw_json"])    #反序列化
                    


