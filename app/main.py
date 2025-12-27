"""
FastAPI 主应用模块

云端音频转乐谱系统 API 入口。
"""

import logging
import uuid
from datetime import timedelta
from pathlib import Path

import aiofiles
from celery.result import AsyncResult
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, HttpUrl

from app.core.auth import (
    Token,
    User,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from app.core.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.audio_tasks import process_audio_task

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="云端音频转乐谱系统 - 将音频文件自动转换为乐谱",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ==================== 请求/响应模型 ====================
class LinkRequest(BaseModel):
    """链接请求模型"""

    url: HttpUrl


class TaskResponse(BaseModel):
    """任务响应模型"""

    task_id: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应模型"""

    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


# ==================== 认证接口 ====================
@app.post("/token", response_model=Token, tags=["认证"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """
    用户登录获取 Token

    - **username**: 用户名 (admin)
    - **password**: 密码 (admin)
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


# ==================== 业务接口 ====================
@app.post("/tasks/upload", response_model=TaskResponse, tags=["任务"])
async def upload_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    """
    上传音频文件创建转换任务

    支持格式: .mp3, .wav, .flac, .ogg, .m4a
    """
    # 验证文件扩展名
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空",
        )

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {settings.ALLOWED_AUDIO_EXTENSIONS}",
        )

    # 生成任务 ID 和文件路径
    task_id = str(uuid.uuid4())
    upload_dir = settings.UPLOAD_DIR / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"original{file_ext}"

    # 保存上传文件（使用流式读取避免大文件 OOM）
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    chunk_size = 1024 * 1024  # 1MB 块

    try:
        total_size = 0
        async with aiofiles.open(file_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                # 边读边检查大小，避免完全读取超大文件
                if total_size > max_size_bytes:
                    # 删除已写入的部分文件
                    await f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件大小超过限制 ({settings.MAX_UPLOAD_SIZE_MB}MB)",
                    )
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"保存文件失败: {e}")
        # 清理可能部分写入的文件
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="保存文件失败",
        )

    # 提交 Celery 任务
    process_audio_task.delay(task_id, str(file_path), is_url=False)

    logger.info(f"用户 {current_user.username} 创建上传任务: {task_id}")
    return TaskResponse(task_id=task_id, message="任务已创建，正在处理中")


@app.post("/tasks/link", response_model=TaskResponse, tags=["任务"])
async def submit_link(
    request: LinkRequest,
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    """
    提交音频链接创建转换任务

    支持 YouTube 等平台链接
    """
    task_id = str(uuid.uuid4())

    # 提交 Celery 任务
    process_audio_task.delay(task_id, str(request.url), is_url=True)

    logger.info(f"用户 {current_user.username} 创建链接任务: {task_id}")
    return TaskResponse(task_id=task_id, message="任务已创建，正在处理中")


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, tags=["任务"])
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    """
    查询任务状态

    状态说明:
    - PENDING: 等待中
    - STARTED: 处理中
    - SUCCESS: 成功
    - FAILURE: 失败
    """
    result = AsyncResult(task_id, app=celery_app)

    response = TaskStatusResponse(
        task_id=task_id,
        status=result.status,
    )

    if result.successful():
        response.result = result.result
    elif result.failed():
        response.error = str(result.result)

    return response


@app.get("/download/{task_id}/{filename}", tags=["下载"])
async def download_file(
    task_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """
    下载生成的结果文件

    - **task_id**: 任务 ID
    - **filename**: 文件名 (如 score.pdf, score.musicxml)
    """
    # 安全检查：防止路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="非法文件名",
        )

    file_path = settings.RESULT_DIR / task_id / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    # 确定 MIME 类型
    suffix = Path(filename).suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".musicxml": "application/vnd.recordare.musicxml+xml",
        ".xml": "application/xml",
        ".mid": "audio/midi",
        ".midi": "audio/midi",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
    )


# ==================== 健康检查 ====================
@app.get("/health", tags=["系统"])
async def health_check() -> dict:
    """健康检查接口"""
    return {"status": "healthy", "service": settings.PROJECT_NAME}


@app.get("/", tags=["系统"])
async def root() -> dict:
    """API 根路径"""
    return {
        "message": f"欢迎使用 {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": "/health",
    }
