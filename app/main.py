from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import word_to_image, word_to_pdf, ocr, pdf_to_word


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.services.ocr_service import get_ocr_engine
        get_ocr_engine()
        print("[lingguang-api] PaddleOCR 模型预加载完成")
    except Exception as e:
        print(f"[lingguang-api] PaddleOCR 预加载失败（OCR 端点将返回 503）: {e}")

    yield

    print("[lingguang-api] 服务关闭")


app = FastAPI(title="LingGuang API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/api/v2/health")
async def health():
    return {"success": True, "message": "LingGuang API Running"}


app.include_router(word_to_image.router, prefix="/api/v2")
app.include_router(word_to_pdf.router, prefix="/api/v2")
app.include_router(ocr.router, prefix="/api/v2")
app.include_router(pdf_to_word.router, prefix="/api/v2")
