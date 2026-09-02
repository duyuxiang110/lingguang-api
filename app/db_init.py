"""
数据库表结构初始化 — 幂等执行，建表+种子数据。
移植自 electron/server/db/init.js
"""
from app.db import query

TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS users (
      id INT PRIMARY KEY AUTO_INCREMENT,
      username VARCHAR(50) NOT NULL UNIQUE,
      email VARCHAR(100) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      avatar VARCHAR(500) DEFAULT NULL,
      phone VARCHAR(20) DEFAULT NULL,
      role ENUM('admin','user','guest') DEFAULT 'user',
      status ENUM('active','inactive','locked','pending') DEFAULT 'active',
      login_attempts INT DEFAULT 0,
      locked_until DATETIME DEFAULT NULL,
      last_login_at DATETIME DEFAULT NULL,
      last_login_ip VARCHAR(45) DEFAULT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_username (username), INDEX idx_email (email), INDEX idx_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS refresh_tokens (
      id INT PRIMARY KEY AUTO_INCREMENT,
      user_id INT NOT NULL,
      token VARCHAR(500) NOT NULL UNIQUE,
      device_info VARCHAR(255) DEFAULT NULL,
      ip_address VARCHAR(45) DEFAULT NULL,
      expires_at DATETIME NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      INDEX idx_token (token(255)), INDEX idx_user_id (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS login_logs (
      id INT PRIMARY KEY AUTO_INCREMENT,
      user_id INT DEFAULT NULL,
      username VARCHAR(50) DEFAULT NULL,
      ip_address VARCHAR(45) DEFAULT NULL,
      device_info VARCHAR(255) DEFAULT NULL,
      action ENUM('login_success','login_failed','logout','token_refresh','password_change') NOT NULL,
      detail TEXT DEFAULT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
      INDEX idx_user_id (user_id), INDEX idx_action (action), INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS sessions (
      id INT PRIMARY KEY AUTO_INCREMENT,
      session_id VARCHAR(64) NOT NULL UNIQUE,
      user_id INT NOT NULL,
      ip_address VARCHAR(45) DEFAULT NULL,
      user_agent VARCHAR(500) DEFAULT NULL,
      is_active TINYINT(1) DEFAULT 1,
      expires_at DATETIME NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      last_activity DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      INDEX idx_session_id (session_id), INDEX idx_user_id (user_id), INDEX idx_active (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS permissions (
      id INT PRIMARY KEY AUTO_INCREMENT,
      name VARCHAR(50) NOT NULL UNIQUE,
      code VARCHAR(100) NOT NULL UNIQUE,
      description VARCHAR(255) DEFAULT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS role_permissions (
      id INT PRIMARY KEY AUTO_INCREMENT,
      role ENUM('admin','user','guest') NOT NULL,
      permission_id INT NOT NULL,
      FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
      UNIQUE KEY uk_role_permission (role, permission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

SEED_SQL = [
    "INSERT IGNORE INTO permissions (name, code, description) VALUES ('用户管理','user:manage','管理所有用户'), ('查看日志','log:view','查看登录日志'), ('系统设置','system:settings','修改系统设置'), ('个人资料','profile:edit','编辑个人资料'), ('基础访问','basic:access','基础系统访问权限')",
    "INSERT IGNORE INTO role_permissions (role, permission_id) SELECT 'admin', id FROM permissions WHERE code IN ('user:manage','log:view','system:settings','profile:edit','basic:access')",
    "INSERT IGNORE INTO role_permissions (role, permission_id) SELECT 'user', id FROM permissions WHERE code IN ('profile:edit','basic:access')",
    "INSERT IGNORE INTO role_permissions (role, permission_id) SELECT 'guest', id FROM permissions WHERE code IN ('basic:access')",
]


def init_database():
    print("[DB] 开始初始化数据库表结构...")
    for sql in TABLES_SQL:
        query(sql)
    for sql in SEED_SQL:
        query(sql)
    print("[DB] 数据库初始化完成 ✓")
