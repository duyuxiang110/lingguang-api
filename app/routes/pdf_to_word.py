import os
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from app.deps import get_auth_payload
from app.concurrency import light_semaphore, heavy_semaphore, check_memory
from app.services.pdf_service import pdf_to_word_text, pdf_to_word_image
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir, cleanup_file
from app.config import MAX_FILE_SIZES

router = APIRouter()


@router.post("/pdf-to-word")
async def pdf_to_word_route(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form(default="text"),
    user: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(file.filename, [".pdf"]):
        raise HTTPException(status_code=422, detail="仅支持 .pdf 格式")
    if file.size and file.size > MAX_FILE_SIZES["pdf_to_word"]:
        raise HTTPException(status_code=413, detail="文件超过 50MB 限制")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="服务器磁盘空间不足")
    if not check_memory(100):
        raise HTTPException(status_code=507, detail="服务器内存不足，请稍后再试")

    content = await file.read()
    input_path = save_upload(content, ".pdf")
    work_dir = create_work_dir()
    output_path = os.path.join(work_dir, "output.docx")

    try:
        semaphore = heavy_semaphore if mode == "image" else light_semaphore
        async with semaphore:
            if await request.is_disconnected():
                raise HTTPException(499, "客户端已取消")
            loop = asyncio.get_event_loop()
            if mode == "image":
                await loop.run_in_executor(None, pdf_to_word_image, input_path, output_path)
            else:
                await loop.run_in_executor(None, pdf_to_word_text, input_path, output_path)

        if await request.is_disconnected():
            raise HTTPException(499, "客户端已取消")

        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=file.filename.replace(".pdf", ".docx"),
            background=background_tasks,
        )
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
