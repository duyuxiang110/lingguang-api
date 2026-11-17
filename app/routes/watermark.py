import os
import asyncio

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from app.deps import get_auth_payload
from app.concurrency import heavy_semaphore, check_memory, release_memory
from app.services.watermark_service import remove_watermark
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir, cleanup_file
from app.config import MAX_FILE_SIZES

router = APIRouter()

IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


@router.post("/remove-watermark")
async def remove_watermark_route(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mask: UploadFile = File(...),
    user: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(file.filename, IMAGE_EXTS):
        raise HTTPException(
            status_code=422, detail="仅支持图片格式 (JPG/PNG/BMP/WEBP)")
    if not validate_file_extension(mask.filename, [".png"]):
        raise HTTPException(status_code=422, detail="蒙版仅支持 PNG 格式")
    if file.size and file.size > MAX_FILE_SIZES["watermark"]:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="服务器磁盘空间不足")
    if not check_memory(100):
        raise HTTPException(status_code=507, detail="服务器内存不足，请稍后再试")

    content = await file.read()
    mask_content = await mask.read()
    ext = os.path.splitext(file.filename)[1].lower()
    input_path = save_upload(content, ext)
    mask_path = save_upload(mask_content, ".png")
    work_dir = create_work_dir()
    output_path = os.path.join(work_dir, f"output{ext}")

    try:
        async with heavy_semaphore:
            if await request.is_disconnected():
                raise HTTPException(499, "客户端已取消")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, remove_watermark, input_path, mask_path, output_path)

        release_memory()

        if await request.is_disconnected():
            raise HTTPException(499, "客户端已取消")

        stem = os.path.splitext(file.filename)[0]
        return FileResponse(
            output_path,
            media_type=MEDIA_TYPES.get(ext, "image/png"),
            filename=f"{stem}_去水印{ext}",
            background=background_tasks,
        )
    except ValueError as e:
        # 空蒙版等业务性错误
        cleanup_dir(work_dir)
        cleanup_file(input_path)
        cleanup_file(mask_path)
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        cleanup_dir(work_dir)
        cleanup_file(input_path)
        cleanup_file(mask_path)
        raise
    except Exception:
        cleanup_dir(work_dir)
        cleanup_file(input_path)
        cleanup_file(mask_path)
        raise HTTPException(status_code=503, detail="AI 模型处理失败，请稍后重试")
    finally:
        background_tasks.add_task(cleanup_dir, work_dir)
        background_tasks.add_task(cleanup_file, input_path)
        background_tasks.add_task(cleanup_file, mask_path)
