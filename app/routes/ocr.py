import os

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from app.deps import get_auth_payload
from app.concurrency import heavy_semaphore
from app.services.ocr_service import recognize_image
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir
from app.config import MAX_FILE_SIZES

router = APIRouter()


@router.post("/ocr")
async def ocr_route(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    lang: str = Form(default="ch"),
    user: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(file.filename, [".jpg", ".jpeg", ".png", ".bmp", ".webp"]):
        raise HTTPException(status_code=422, detail="仅支持图片格式 (JPG/PNG/BMP/WEBP)")
    if file.size and file.size > MAX_FILE_SIZES["ocr"]:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="服务器磁盘空间不足")

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()
    input_path = save_upload(content, ext)
    work_dir = create_work_dir()

    try:
        async with heavy_semaphore:
            result = recognize_image(input_path, lang=lang)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        background_tasks.add_task(cleanup_dir, work_dir)
