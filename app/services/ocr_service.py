_ocr_engine = None


def get_ocr_engine():
    """懒加载 PaddleOCR 引擎（首次调用时初始化，之后常驻内存）。"""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            use_gpu=False,
            show_log=False,
        )
    return _ocr_engine


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

    return {"text": full_text, "confidence": avg_confidence}
