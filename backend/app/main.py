from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.router import api_router
from app.core.config import settings

STATUS = {"application": "UniShop China API", "status": "running", "version": "1.0.0"}

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield

app = FastAPI(title=f"{settings.app_name} API", version="1.0.0", debug=settings.app_debug, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router, prefix=settings.api_v1_prefix)

@app.get("/", tags=["health"])
def root(): return STATUS

@app.get("/health", tags=["health"])
def health(): return STATUS

@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
