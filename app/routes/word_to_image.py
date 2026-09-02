import os
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from app.deps import get_auth_payload
from app.concurrency import heavy_semaphore
from app.services.word_service import word_to_images
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir
from app.config import MAX_FILE_SIZES

router = APIRouter()


@router.post("/word-to-image")
async def word_to_image_route(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dpi: int = Form(default=150),
    format: str = Form(default="png"),
    user: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(file.filename, [".docx"]):
        raise HTTPException(status_code=422, detail="仅支持 .docx 格式")
    if file.size and file.size > MAX_FILE_SIZES["word_to_image"]:
        raise HTTPException(status_code=413, detail="文件超过 30MB 限制")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="服务器磁盘空间不足")

    content = await file.read()
    input_path = save_upload(content, ".docx")
    work_dir = create_work_dir()

    try:
        async with heavy_semaphore:
            images = await word_to_images(input_path, work_dir, dpi=dpi, fmt=format)
        return {"success": True, "data": {"images": images}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        background_tasks.add_task(cleanup_dir, work_dir)
