"""去水印服务 — LaMa AI 模型对用户涂抹区域做 inpainting 重绘。

- 推理内核用 simple-lama-inpainting（需 Python>=3.10）：0.1.2 已修复
  jit.load 未传 map_location 导致 CPU 环境报 aten::empty_strided CUDA 的问题；
  其输出为 pad 到 8 倍数的尺寸，本模块负责裁回原尺寸
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

_lama = None


def _get_lama():
    """懒加载 SimpleLama 单例，返回 callable(PIL image, PIL mask) -> PIL image。

    模型路径由包内读 LAMA_MODEL 环境变量（服务器预置），未设置时自动下载到
    torch hub 缓存。懒导入避免模块加载时拉起 torch。
    """
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    return _lama


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
    margin = max(int(max(x1 - x0, y1 - y0) *
                 CROP_MARGIN_RATIO), CROP_MARGIN_MIN)
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
        # SimpleLama 输出为 pad 到 8 倍数的尺寸，裁回原图大小
        if result.size != (w, h):
            result = result.crop((0, 0, w, h))
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
        # 先裁掉 8 倍数 pad，再恢复降采样前的裁剪区尺寸
        if sub_res.size != sub_img.size:
            sub_res = sub_res.crop((0, 0, sub_img.size[0], sub_img.size[1]))
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
