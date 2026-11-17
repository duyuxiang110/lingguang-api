"""去水印服务单元测试 — mock LaMa 模型（不下载、不加载 torch 模型）"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services import watermark_service


class FakeLama:
    """替身模型：记录入参，返回纯绿色结果图（便于断言贴回逻辑）"""

    def __init__(self, calls):
        self.calls = calls

    def __call__(self, image, mask):
        self.calls.append({"image": image, "mask": mask})
        return Image.new("RGB", image.size, (0, 255, 0))


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    monkeypatch.setattr(watermark_service, "_get_lama", lambda: FakeLama(recorded))
    return recorded


def _make_image(path, size, color=(123, 200, 90)):
    Image.new("RGB", size, color).save(path)


def _make_mask(path, size, box=None):
    """黑底蒙版；box=(x0,y0,x1,y1) 画白色矩形，None 为全黑"""
    m = Image.new("L", size, 0)
    if box is not None:
        ImageDraw.Draw(m).rectangle(box, fill=255)
    m.save(path)


def test_small_image_whole_path(tmp_path, calls):
    """小图走整图推理：输出尺寸不变，且结果来自模型"""
    img = tmp_path / "in.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (200, 120))
    _make_mask(msk, (200, 120), (50, 40, 80, 60))

    result = watermark_service.remove_watermark(str(img), str(msk), str(out))

    assert result == str(out)
    assert len(calls) == 1
    assert calls[0]["image"].size == (200, 120)
    opened = Image.open(out)
    assert opened.format == "PNG"
    assert opened.size == (200, 120)
    assert opened.convert("RGB").getpixel((10, 10)) == (0, 255, 0)


def test_jpg_output_format(tmp_path, calls):
    """输出 .jpg 时保存为 JPEG 格式"""
    img = tmp_path / "in.jpg"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.jpg"
    _make_image(img, (160, 100))
    _make_mask(msk, (160, 100), (10, 10, 30, 30))

    watermark_service.remove_watermark(str(img), str(msk), str(out))

    assert Image.open(out).format == "JPEG"


def test_mask_resized_to_image(tmp_path, calls):
    """蒙版尺寸与原图不一致时，resize 到原图尺寸再送模型"""
    img = tmp_path / "in.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (200, 120))
    _make_mask(msk, (100, 60), (25, 20, 40, 30))  # 一半尺寸

    watermark_service.remove_watermark(str(img), str(msk), str(out))

    mask_arr = np.array(calls[0]["mask"])
    assert mask_arr.shape[:2] == (120, 200)  # (h, w)


def test_mask_binarized_and_dilated(tmp_path, calls):
    """单个白像素经二值化+膨胀后扩大为 5x5 区域（覆盖水印边缘光晕）"""
    img = tmp_path / "in.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (200, 120))
    m = Image.new("L", (200, 120), 0)
    m.putpixel((100, 60), 255)
    m.save(msk)

    watermark_service.remove_watermark(str(img), str(msk), str(out))

    mask_arr = np.array(calls[0]["mask"])
    assert (mask_arr > 127).sum() >= 25


def test_large_image_crop_paste_back(tmp_path, calls):
    """大图（长边>1600）走裁剪-修复-贴回：推理图受限，修复区外像素无损"""
    img = tmp_path / "big.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (3000, 2000), (123, 200, 90))
    _make_mask(msk, (3000, 2000), (100, 100, 300, 250))

    watermark_service.remove_watermark(str(img), str(msk), str(out))

    assert len(calls) == 1
    sub_img = calls[0]["image"]
    assert max(sub_img.size) <= watermark_service.MAX_INFERENCE_SIDE
    # 裁剪区域带 margin，比蒙版包围盒大，但不超过整图
    assert sub_img.size[0] > 200 and sub_img.size[1] > 150
    assert sub_img.size != (3000, 2000)

    opened = Image.open(out).convert("RGB")
    assert opened.size == (3000, 2000)
    # 修复区内是模型输出的绿色
    assert opened.getpixel((200, 180)) == (0, 255, 0)
    # 远离修复区的像素保持原样（无损）
    assert opened.getpixel((0, 0)) == (123, 200, 90)
    assert opened.getpixel((2999, 1999)) == (123, 200, 90)


def test_empty_mask_raises(tmp_path, calls):
    """全黑蒙版直接报 ValueError，不调模型"""
    img = tmp_path / "in.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (200, 120))
    _make_mask(msk, (200, 120), None)

    with pytest.raises(ValueError):
        watermark_service.remove_watermark(str(img), str(msk), str(out))
    assert len(calls) == 0


def test_model_error_propagates(tmp_path, monkeypatch):
    """模型加载/推理异常向上抛，由路由层转 503"""
    def broken():
        raise RuntimeError("model download failed")

    monkeypatch.setattr(watermark_service, "_get_lama", broken)
    img = tmp_path / "in.png"
    msk = tmp_path / "m.png"
    out = tmp_path / "out.png"
    _make_image(img, (200, 120))
    _make_mask(msk, (200, 120), (50, 40, 80, 60))

    with pytest.raises(RuntimeError):
        watermark_service.remove_watermark(str(img), str(msk), str(out))
