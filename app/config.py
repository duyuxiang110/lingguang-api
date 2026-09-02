import os

# ===== MySQL =====
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Abc3622490"),
    "database": os.environ.get("DB_NAME", "sso_system"),
}

# ===== JWT =====
JWT_SECRET = os.environ.get("JWT_SECRET", "sso-secret-key-change-in-production-2024")
JWT_REFRESH_SECRET = os.environ.get("JWT_REFRESH_SECRET", "sso-refresh-secret-key-change-in-production-2024")
JWT_ACCESS_EXPIRY = "2h"
JWT_REFRESH_EXPIRY = "7d"

# ===== 安全 =====
BCRYPT_ROUNDS = 12
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_TIME_MIN = 15
LOGIN_RATE_LIMIT_WINDOW_SEC = 60
LOGIN_RATE_LIMIT_MAX = 5
LOGIN_IP_LOCK_MIN = 10

# ===== 文件处理 =====
UPLOAD_DIR = "/tmp/lingguang/uploads"
WORK_DIR = "/tmp/lingguang/work"
OUTPUT_DIR = "/tmp/lingguang/output"

MAX_FILE_SIZES = {
    "word_to_image": 30 * 1024 * 1024,
    "word_to_pdf": 30 * 1024 * 1024,
    "ocr": 10 * 1024 * 1024,
    "pdf_to_word": 50 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
}

LIBREOFFICE_TIMEOUT = 60
DISK_SPACE_THRESHOLD = 500 * 1024 * 1024

for d in [UPLOAD_DIR, WORK_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)
