import os

JWT_SECRET = os.environ.get("JWT_SECRET", "sso-secret-key-change-in-production-2024")

UPLOAD_DIR = "/tmp/lingguang/uploads"
WORK_DIR = "/tmp/lingguang/work"
OUTPUT_DIR = "/tmp/lingguang/output"

MAX_FILE_SIZES = {
    "word_to_image": 30 * 1024 * 1024,
    "word_to_pdf": 30 * 1024 * 1024,
    "ocr": 10 * 1024 * 1024,
    "pdf_to_word": 50 * 1024 * 1024,
}

LIBREOFFICE_TIMEOUT = 60
DISK_SPACE_THRESHOLD = 500 * 1024 * 1024

for d in [UPLOAD_DIR, WORK_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)
