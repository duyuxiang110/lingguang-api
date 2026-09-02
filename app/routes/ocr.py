import os
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from app.deps import get_auth_payload
from app.concurrency import heavy_semaphore, check_memory
from app.services.ocr_service import recognize_image
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir, cleanup_file
from app.config import MAX_FILE_SIZES

router = APIRouter()


@router.post("/ocr")
async def ocr_route(
    request: Request,
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
    if not check_memory(400):
        raise HTTPException(status_code=507, detail="服务器内存不足，请稍后再试")

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()
    input_path = save_upload(content, ext)
    work_dir = create_work_dir()

    try:
        async with heavy_semaphore:
            if await request.is_disconnected():
                raise HTTPException(499, "客户端已取消")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, recognize_image, input_path, lang)
        return {"success": True, "data": result}
    except HTTPException:
        cleanup_dir(work_dir)
        cleanup_file(input_path)
        raise
    except Exception as e:
        cleanup_dir(work_dir)
        cleanup_file(input_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        background_tasks.add_task(cleanup_dir, work_dir)
        background_tasks.add_task(cleanup_file, input_path)
