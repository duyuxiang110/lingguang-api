"""
视频工具路由 — 视频信息/压缩转格式。
移植自 electron/server/routes/tools.js，用系统 ffmpeg + asyncio subprocess。
"""
import os
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from app.deps import get_auth_payload
from app.concurrency import light_semaphore
from app.utils import validate_file_extension, check_disk_space, create_work_dir, cleanup_dir
from app.config import MAX_FILE_SIZES

router = APIRouter()

VIDEO_EXTS = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".ts", ".mpeg", ".mpg"]

QUALITY_CRF = {"high": "22", "medium": "28", "low": "34"}
RESOLUTION_SCALE = {"original": None, "1080p": "scale=-2:1080", "720p": "scale=-2:720", "480p": "scale=-2:480"}
FORMAT_CONFIG = {
    "mp4": {"vcodec": "libx264", "acodec": "aac", "ext": ".mp4", "mime": "video/mp4"},
    "webm": {"vcodec": "libvpx-vp9", "acodec": "libopus", "ext": ".webm", "mime": "video/webm"},
    "avi": {"vcodec": "libx264", "acodec": "mp3", "ext": ".avi", "mime": "video/x-msvideo"},
    "mov": {"vcodec": "libx264", "acodec": "aac", "ext": ".mov", "mime": "video/quicktime"},
    "mkv": {"vcodec": "libx264", "acodec": "aac", "ext": ".mkv", "mime": "video/x-matroska"},
    "gif": {"vcodec": None, "acodec": None, "ext": ".gif", "mime": "image/gif"},
}


async def _run_ffprobe(path: str) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    import json
    meta = json.loads(stdout)
    vs = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
    fmt = meta.get("format", {})
    return {
        "duration": float(fmt.get("duration", 0)),
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "bitrate": int(fmt.get("bit_rate", 0)),
        "size": int(fmt.get("size", 0)),
        "formatName": fmt.get("format_name", ""),
    }


@router.post("/v2/video-info")
async def video_info(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    _payload: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(video.filename, VIDEO_EXTS):
        raise HTTPException(422, detail={"success": False, "message": "不支持的视频格式"})
    if video.size and video.size > MAX_FILE_SIZES["video"]:
        raise HTTPException(413, detail={"success": False, "message": "文件超过 500MB 限制"})
    if not check_disk_space():
        raise HTTPException(507, detail={"success": False, "message": "服务器磁盘空间不足"})

    content = await video.read()
    ext = os.path.splitext(video.filename)[1].lower()
    from app.utils import save_upload
    input_path = save_upload(content, ext)
    work_dir = create_work_dir()

    try:
        async with light_semaphore:
            info = await _run_ffprobe(input_path)
        return {"success": True, "data": info}
    except Exception as e:
        raise HTTPException(500, detail={"success": False, "message": str(e)})
    finally:
        background_tasks.add_task(cleanup_dir, work_dir)
        try:
            os.unlink(input_path)
        except OSError:
            pass


@router.post("/v2/video-compress")
async def video_compress(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    format: str = Form("mp4"),
    quality: str = Form("medium"),
    resolution: str = Form("original"),
    _payload: dict = Depends(get_auth_payload),
):
    if not validate_file_extension(video.filename, VIDEO_EXTS):
        raise HTTPException(422, detail={"success": False, "message": "不支持的视频格式"})
    if video.size and video.size > MAX_FILE_SIZES["video"]:
        raise HTTPException(413, detail={"success": False, "message": "文件超过 500MB 限制"})
    if not check_disk_space():
        raise HTTPException(507, detail={"success": False, "message": "服务器磁盘空间不足"})

    fmt = FORMAT_CONFIG.get(format)
    if not fmt:
        raise HTTPException(400, detail={"success": False, "message": f"不支持的输出格式: {format}"})

    content = await video.read()
    ext = os.path.splitext(video.filename)[1].lower()
    from app.utils import save_upload
    input_path = save_upload(content, ext)
    work_dir = create_work_dir()
    output_name = os.path.basename(input_path).replace("upload_", "output_").replace(ext, "") + fmt["ext"]
    output_path = os.path.join(work_dir, output_name)

    try:
        crf = QUALITY_CRF.get(quality, "28")
        scale = RESOLUTION_SCALE.get(resolution)

        cmd = ["ffmpeg", "-i", input_path]
        if format == "gif":
            filters = ["fps=12"]
            if scale:
                filters.append(scale)
            else:
                filters.append("scale=-2:-2")
            cmd += ["-vf", ",".join(filters), "-loop", "0"]
        else:
            cmd += ["-c:v", fmt["vcodec"], "-c:a", fmt["acodec"], "-crf", crf, "-preset", "fast"]
            if scale:
                cmd += ["-vf", scale]
            if format == "mp4":
                cmd += ["-movflags", "+faststart"]
        cmd += ["-y", output_path]

        async with light_semaphore:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg 处理失败: {stderr.decode()[:500]}")

        if not os.path.exists(output_path):
            raise RuntimeError("压缩输出文件不存在")

        stat = os.stat(output_path)
        original = os.path.splitext(video.filename)[0]
        download_name = f"{original}_compressed{fmt['ext']}"

        def cleanup():
            try:
                os.unlink(input_path)
                os.unlink(output_path)
            except OSError:
                pass

        background_tasks.add_task(cleanup)

        def iterfile():
            with open(output_path, "rb") as f:
                yield from f

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{download_name}",
            "X-Output-Size": str(stat.st_size),
        }
        return StreamingResponse(iterfile(), media_type=fmt["mime"], headers=headers)
    except Exception as e:
        for p in [input_path, output_path]:
            try:
                os.unlink(p)
            except OSError:
                pass
        raise HTTPException(500, detail={"success": False, "message": str(e)})
