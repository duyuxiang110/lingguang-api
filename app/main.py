from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import word_to_image, word_to_pdf, ocr, pdf_to_word, auth, users, video


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.db import init_pool
        init_pool()
    except Exception as e:
        print(f"[lingguang-api] MySQL 初始化失败: {e}")

    try:
        from app.db_init import init_database
        init_database()
    except Exception as e:
        print(f"[lingguang-api] 数据库表初始化失败: {e}")

    # PaddleOCR 不再预加载 — 节省 ~500MB 空闲内存
    # OCR 引擎将在首次请求时懒加载

    yield
    print("[lingguang-api] 服务关闭")


app = FastAPI(title="LingGuang API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if hasattr(exc, "status_code") and hasattr(exc, "detail"):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@app.get("/api/v2/health")
async def health():
    return {"success": True, "message": "LingGuang API Running"}


# Auth + Users + Video tools (prefix /api)
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(video.router, prefix="/api")

# Processing endpoints (prefix /api/v2)
app.include_router(word_to_image.router, prefix="/api/v2")
app.include_router(word_to_pdf.router, prefix="/api/v2")
app.include_router(ocr.router, prefix="/api/v2")
app.include_router(pdf_to_word.router, prefix="/api/v2")
