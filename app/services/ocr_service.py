import gc
import ctypes


def recognize_image(image_path: str, lang: str = "ch") -> dict:
    """识别图片中的文字，返回 {text, confidence}。

    每次调用加载 PaddleOCR 模型，用完立即卸载，不常驻内存。
    代价是每次 OCR 多 ~10 秒模型加载时间，但省 ~500MB 内存。
    """
    from paddleocr import PaddleOCR

    engine = PaddleOCR(
        use_angle_cls=True,
        lang="ch",
        use_gpu=False,
        show_log=False,
    )

    result = engine.ocr(image_path, cls=True)

    # 立即卸载模型
    del engine
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

    texts = []
    confidences = []
    for line in result:
        if line is None:
            continue
        for item in line:
            texts.append(item[1][0])
            confidences.append(item[1][1])

    full_text = "\n".join(texts)
    avg_confidence = round(sum(confidences) / len(confidences) * 100) if confidences else 0

    del result
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

    return {"text": full_text, "confidence": avg_confidence}
