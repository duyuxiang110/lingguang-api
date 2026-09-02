"""
MySQL 连接池管理 — pymysql + DBUtils，带自动重试。
参照 Express db/pool.js 的重试逻辑。
"""
import pymysql
from dbutils.pooled_db import PooledDB
from app.config import DB_CONFIG

_pool: PooledDB | None = None

RETRYABLE_ERRORS = ("ETIMEDOUT", "ECONNRESET", "EPIPE", "PROTOCOL_CONNECTION_LOST", "2006", "2013")


def init_pool():
    global _pool
    if _pool is not None:
        return _pool
    _pool = PooledDB(
        creator=pymysql,
        mincached=2,
        maxcached=5,
        maxconnections=5,
        blocking=True,
        ping=1,
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        conn = _pool.connection()
        conn.close()
        print(f"[DB] MySQL 连接成功: {DB_CONFIG['host']}")
    except Exception as e:
        _pool = None
        print(f"[DB] MySQL 连接失败: {e}")
        raise
    return _pool


def query(sql: str, params=None, retries=2):
    if _pool is None:
        raise RuntimeError("数据库连接池未初始化")
    err = None
    for _ in range(retries + 1):
        try:
            conn = _pool.connection()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchall()
                return cur.lastrowid
        except Exception as e:
            err = e
            code = getattr(e, "args", ("",))[0] if e.args else ""
            msg = str(e)
            if any(k in msg or str(code) == k for k in RETRYABLE_ERRORS) and retries > 0:
                import time
                time.sleep(1)
                retries -= 1
                continue
            raise
    raise err
