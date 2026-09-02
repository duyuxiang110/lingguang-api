import asyncio
import os
import glob
import base64

from app.config import LIBREOFFICE_TIMEOUT
from app.concurrency import run_subprocess_safe


async def libreoffice_convert(input_path: str, output_dir: str, target_format: str, request=None) -> str:
    """LibreOffice headless 转换，返回输出文件路径。"""
    cmd = [
        "libreoffice", "--headless", "--norestore", "--nolockcheck",
        "--convert-to", target_format,
        "--outdir", output_dir,
        input_path,
    ]

    if request is not None:
        stdout, stderr, returncode = await run_subprocess_safe(request, cmd, timeout=LIBREOFFICE_TIMEOUT)
        if returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {stderr.decode(errors='replace').strip()}")
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=LIBREOFFICE_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"LibreOffice 转换超时（{LIBREOFFICE_TIMEOUT}秒），文件可能损坏")

        if proc.returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {stderr.decode(errors='replace').strip()}")

    base = os.path.splitext(os.path.basename(input_path))[0]
    ext = "pdf" if target_format.startswith("pdf") else target_format.split(":")[0]
    output_path = os.path.join(output_dir, f"{base}.{ext}")

    if not os.path.exists(output_path):
        matches = glob.glob(os.path.join(output_dir, f"{base}.*"))
        if matches:
            output_path = matches[0]
        else:
            raise RuntimeError("LibreOffice 转换完成但未找到输出文件")

    return output_path


def render_pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 150, fmt: str = "png") -> list:
    """用 pdf2image 将 PDF 每页渲染为图片，返回图片路径列表。"""
    from pdf2image import convert_from_path

    fmt_ext = "jpg" if fmt == "image/jpeg" else "png"
    images = convert_from_path(pdf_path, dpi=dpi, fmt=fmt_ext, output_folder=output_dir)
    paths = []
    for i, img in enumerate(images):
        path = os.path.join(output_dir, f"page_{i:04d}.{fmt_ext}")
        img.save(path, fmt_ext.upper(), quality=92 if fmt_ext == "jpg" else None)
        paths.append(path)
    return paths


def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


async def word_to_images(input_path: str, work_dir: str, dpi: int = 150, fmt: str = "png", request=None) -> list:
    """Word → PDF (LibreOffice) → Images (pdf2image)，返回 base64 列表。"""
    pdf_path = await libreoffice_convert(input_path, work_dir, "pdf", request=request)
    fmt_arg = "image/jpeg" if fmt == "jpg" else "image/png"
    image_paths = render_pdf_to_images(pdf_path, work_dir, dpi=dpi, fmt=fmt_arg)
    return [image_to_base64(p) for p in image_paths]


async def word_to_pdf_file(input_path: str, work_dir: str, request=None) -> str:
    """Word → PDF (LibreOffice)，返回 PDF 文件路径。"""
    return await libreoffice_convert(input_path, work_dir, "pdf", request=request)
