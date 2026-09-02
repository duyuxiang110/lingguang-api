import os
import uuid
import shutil

from app.config import UPLOAD_DIR, DISK_SPACE_THRESHOLD


def validate_file_extension(filename: str, allowed_exts: list) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in [e.lower() for e in allowed_exts]


def check_disk_space(path: str = "/tmp") -> bool:
    usage = shutil.disk_usage(path)
    return usage.free >= DISK_SPACE_THRESHOLD


def save_upload(content: bytes, ext: str) -> str:
    filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def create_work_dir() -> str:
    dirname = f"job_{uuid.uuid4().hex[:8]}"
    path = os.path.join("/tmp/lingguang/work", dirname)
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_dir(path: str) -> None:
    try:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def cleanup_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass
