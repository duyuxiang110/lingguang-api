import gc
import time
import threading

_ocr_engine = None
_ocr_lock = threading.Lock()
_ocr_last_used = 0.0
_OCR_IDLE_TIMEOUT = 300  # 5 分钟空闲后卸载模型


def get_ocr_engine():
    """懒加载 PaddleOCR 引擎（首次调用时初始化，之后常驻内存）。"""
    global _ocr_engine, _ocr_last_used
    with _ocr_lock:
        if _ocr_engine is None:
            from paddleocr import PaddleOCR
            _ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                use_gpu=False,
                show_log=False,
            )
        _ocr_last_used = time.time()
        return _ocr_engine


def unload_ocr_engine_if_idle():
    """如果 OCR 引擎空闲超过 5 分钟，卸载释放内存。"""
    global _ocr_engine
    with _ocr_lock:
        if _ocr_engine is not None and (time.time() - _ocr_last_used) > _OCR_IDLE_TIMEOUT:
            del _ocr_engine
            _ocr_engine = None
            gc.collect()
            try:
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception:
                pass
            print("[lingguang-api] PaddleOCR 模型空闲超时，已卸载释放 ~500MB 内存")
            return True
    return False


def recognize_image(image_path: str, lang: str = "ch") -> dict:
    """识别图片中的文字，返回 {text, confidence}。"""
    engine = get_ocr_engine()
    result = engine.ocr(image_path, cls=True)

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
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

    return {"text": full_text, "confidence": avg_confidence}
