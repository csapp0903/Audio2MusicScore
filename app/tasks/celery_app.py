"""
Celery 应用配置模块
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "audio2musicscore",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.audio_tasks"],
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 任务结果过期时间（1天）
    result_expires=86400,
    # 任务执行时间限制（30分钟）
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
