from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from app.deps import get_auth_payload
from app.concurrency import heavy_semaphore, check_memory
from app.services.word_service import word_to_pdf_file
from app.utils import validate_file_extension, check_disk_space, save_upload, create_work_dir, cleanup_dir, cleanup_file
from app.config import MAX_FILE_SIZES

router = APIRouter()


@router.post("/word-to-pdf")
async def word_to_pdf_route(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(file.filename, [".docx"]):
        raise HTTPException(status_code=422, detail="仅支持 .docx 格式")
    if file.size and file.size > MAX_FILE_SIZES["word_to_pdf"]:
        raise HTTPException(status_code=413, detail="文件超过 30MB 限制")
    if not check_disk_space():
        raise HTTPException(status_code=507, detail="服务器磁盘空间不足")
    if not check_memory(100):
        raise HTTPException(status_code=507, detail="服务器内存不足，请稍后再试")

    content = await file.read()
    input_path = save_upload(content, ".docx")
    work_dir = create_work_dir()

    try:
        async with heavy_semaphore:
            if await request.is_disconnected():
                raise HTTPException(499, "客户端已取消")
            pdf_path = await word_to_pdf_file(input_path, work_dir, request=request)
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=file.filename.replace(".docx", ".pdf"),
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
