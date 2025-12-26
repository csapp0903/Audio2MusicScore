"""
应用配置模块

使用 Pydantic BaseSettings 管理所有配置项，支持环境变量覆盖。
"""

import secrets
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ==================== 基础路径配置 ====================
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    RESULT_DIR: Path = BASE_DIR / "results"
    TEMP_DIR: Path = BASE_DIR / "temp"

    # ==================== Redis 配置 ====================
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==================== Celery 配置 ====================
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # ==================== JWT 配置 ====================
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时

    # ==================== 文件上传配置 ====================
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_AUDIO_EXTENSIONS: set[str] = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}

    # ==================== MuseScore 配置 ====================
    MUSESCORE_PATH: str = "/usr/bin/musescore"
    USE_XVFB: bool = True  # 无头服务器需要使用 xvfb-run

    # ==================== API 配置 ====================
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Audio2MusicScore"
    DEBUG: bool = False

    def ensure_directories(self) -> None:
        """确保所有必要的目录存在"""
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.RESULT_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    settings = Settings()
    settings.ensure_directories()
    return settings


# 全局配置实例
settings = get_settings()
