"""去水印服务 — LaMa AI 模型对用户涂抹区域做 inpainting 重绘。

- 直接加载 big-lama TorchScript（不用 simple-lama-inpainting 包：其 jit.load
  未传 map_location，对 CUDA trace 的模型在新版 torch CPU 环境会报
  aten::empty_strided CUDA 错误）
- 模型懒加载后常驻内存（约 500MB），受 heavy_semaphore 保护串行调用
- 大图（长边 > MAX_INFERENCE_SIDE）自动走「裁剪-修复-贴回」策略：
  只裁蒙版包围盒 + margin 区域推理，避免撑爆 systemd MemoryMax；
  修复区外的像素原样保留，无清晰度损失
- 模型异常直接上抛（由路由层转 503），不做传统算法兜底，避免静默劣质结果
"""
import os

import cv2
import numpy as np
from PIL import Image

# 单次推理的长边上限，超过则裁剪局部处理（受服务器 MemoryMax 约束）
MAX_INFERENCE_SIDE = int(os.environ.get("LAMA_MAX_SIDE", "1600"))
# 蒙版膨胀核大小：盖住水印半透明边缘光晕，避免残留描边
DILATE_KERNEL = 5
# 大图裁剪时蒙版包围盒外扩比例 / 最小像素
CROP_MARGIN_RATIO = 0.15
CROP_MARGIN_MIN = 64
# big-lama TorchScript 模型（约 196MB），与 IOPaint/simple-lama 同源
LAMA_MODEL_URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"

_lama = None


def _model_path() -> str:
    """模型路径：优先 LAMA_MODEL 环境变量（服务器预置），否则 torch hub 缓存，缺失时自动下载"""
    env_path = os.environ.get("LAMA_MODEL")
    if env_path:
        if not os.path.exists(env_path):
            raise FileNotFoundError(f"LaMa 模型文件不存在: {env_path}，请先预置 big-lama.pt")
        return env_path
    from torch.hub import download_url_to_file, get_dir
    cached = os.path.join(get_dir(), "checkpoints", "big-lama.pt")
    if not os.path.exists(cached):
        os.makedirs(os.path.dirname(cached), exist_ok=True)
        download_url_to_file(LAMA_MODEL_URL, cached, progress=True)
    return cached


def _lama_inpaint(image: Image.Image, mask: Image.Image) -> Image.Image:
    """用已加载的 TorchScript 模型修复：归一化 → pad 到 8 倍数 → 推理 → 裁回原尺寸"""
    import torch

    model = _lama
    arr = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    img_t = torch.from_numpy(np.transpose(arr, (2, 0, 1))).unsqueeze(0)
    mask_arr = np.array(mask.convert("L"))
    msk_t = torch.from_numpy((mask_arr > 0).astype(np.float32)).unsqueeze(0).unsqueeze(0)

    h, w = img_t.shape[2], img_t.shape[3]
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    if ph or pw:
        img_t = torch.nn.functional.pad(img_t, (0, pw, 0, ph), mode="reflect")
        msk_t = torch.nn.functional.pad(msk_t, (0, pw, 0, ph), mode="constant", value=0)

    with torch.inference_mode():
        res = model(img_t, msk_t)
    res = res[0].permute(1, 2, 0).numpy()[:h, :w]
    return Image.fromarray(np.clip(res * 255, 0, 255).astype(np.uint8))


def _get_lama():
    """懒加载 LaMa 模型单例，返回 callable(PIL image, PIL mask) -> PIL image"""
    global _lama
    if _lama is None:
        import torch
        model = torch.jit.load(_model_path(), map_location="cpu")
        model.eval()
        _lama = model
    return _lama_inpaint


def _load_mask(image_size: tuple, mask_path: str) -> np.ndarray:
    """读蒙版 → 灰度 → 对齐原图尺寸 → 二值化 → 膨胀，返回单通道 uint8 (0/255)"""
    mask = Image.open(mask_path).convert("L")
    if mask.size != image_size:
        mask = mask.resize(image_size, Image.NEAREST)
    _, binary = cv2.threshold(np.array(mask), 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((DILATE_KERNEL, DILATE_KERNEL), np.uint8)
    return cv2.dilate(binary, kernel)


def _crop_bounds(mask: np.ndarray, img_w: int, img_h: int) -> tuple:
    """蒙版包围盒外扩 margin 并夹到图像范围内，返回 (x0, x1, y0, y1)"""
    ys, xs = np.where(mask > 0)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    margin = max(int(max(x1 - x0, y1 - y0) * CROP_MARGIN_RATIO), CROP_MARGIN_MIN)
    return (
        max(0, x0 - margin),
        min(img_w, x1 + margin + 1),
        max(0, y0 - margin),
        min(img_h, y1 + margin + 1),
    )


def remove_watermark(image_path: str, mask_path: str, output_path: str) -> str:
    """对 image 的 mask 白色区域做 AI 重绘，结果保存到 output_path。

    mask 为空时抛 ValueError；模型加载/推理失败时异常上抛。
    """
    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    mask = _load_mask((w, h), mask_path)
    if not mask.any():
        raise ValueError("蒙版为空，请先涂抹水印区域")

    lama = _get_lama()

    if max(w, h) <= MAX_INFERENCE_SIDE:
        result = lama(image, Image.fromarray(mask))
    else:
        arr = np.array(image)
        x0, x1, y0, y1 = _crop_bounds(mask, w, h)
        sub_img = Image.fromarray(arr[y0:y1, x0:x1])
        sub_mask = Image.fromarray(mask[y0:y1, x0:x1])
        sw, sh = sub_img.size
        if max(sw, sh) > MAX_INFERENCE_SIDE:
            f = MAX_INFERENCE_SIDE / max(sw, sh)
            new_size = (max(1, round(sw * f)), max(1, round(sh * f)))
            sub_img = sub_img.resize(new_size, Image.LANCZOS)
            sub_mask = sub_mask.resize(new_size, Image.NEAREST)
        sub_res = lama(sub_img, sub_mask)
        if sub_res.size != (sw, sh):
            sub_res = sub_res.resize((sw, sh), Image.LANCZOS)
        arr[y0:y1, x0:x1] = np.array(sub_res.convert("RGB"))
        result = Image.fromarray(arr)

    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        result.convert("RGB").save(output_path, quality=95)
    else:
        result.save(output_path)
    return output_path
