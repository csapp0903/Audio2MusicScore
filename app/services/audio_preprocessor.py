"""
音频预处理服务模块

负责：
1. 使用 yt-dlp 从 URL 下载音频
2. 使用 ffmpeg 转换音频格式（16kHz mono WAV）
"""

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.core.utils import run_command, CommandError

logger = logging.getLogger(__name__)

# 标准化音频参数（适配 AI 模型）
# 注意：Basic Pitch 模型设计用于 22050Hz 采样率
# 使用较低的采样率会导致高频信息丢失，影响音高检测精度
TARGET_SAMPLE_RATE = 22050  # 22.05kHz，保留更多高频信息
TARGET_CHANNELS = 1  # mono


def download_audio_from_url(url: str, output_dir: Path) -> Path:
    """
    使用 yt-dlp 从 URL 下载音频

    Args:
        url: 音频/视频 URL（支持 YouTube 等平台）
        output_dir: 输出目录

    Returns:
        Path: 下载并转换后的 WAV 文件路径

    Raises:
        CommandError: 下载失败时抛出
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "downloaded.wav"

    logger.info(f"开始从 URL 下载音频: {url}")

    # yt-dlp 命令参数说明：
    # -x: 仅提取音频
    # --audio-format wav: 转换为 WAV 格式
    # --audio-quality 0: 最高质量
    # --postprocessor-args: 传递给 ffmpeg 的参数，设置采样率和声道
    # -o: 输出文件路径
    cmd = [
        "yt-dlp",
        "-x",  # 提取音频
        "--audio-format", "wav",
        "--audio-quality", "0",
        # 使用 ffmpeg 后处理，转换为 16kHz mono
        "--postprocessor-args",
        f"ffmpeg:-ar {TARGET_SAMPLE_RATE} -ac {TARGET_CHANNELS}",
        "-o", str(output_file),
        "--no-playlist",  # 不下载播放列表
        "--quiet",  # 减少输出
        url,
    ]

    run_command(cmd, timeout=600)  # 10分钟超时

    if not output_file.exists():
        raise CommandError(
            message=f"下载完成但文件不存在: {output_file}",
            returncode=-1,
            stderr="File not found after download",
        )

    logger.info(f"音频下载完成: {output_file}")
    return output_file


def convert_audio_to_wav(input_file: Path, output_dir: Path) -> Path:
    """
    使用 ffmpeg 将音频转换为标准 WAV 格式

    转换参数：
    - 采样率: 16000 Hz
    - 声道: mono (单声道)
    - 格式: 16-bit PCM WAV

    Args:
        input_file: 输入音频文件路径
        output_dir: 输出目录

    Returns:
        Path: 转换后的 WAV 文件路径

    Raises:
        CommandError: 转换失败时抛出
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "converted.wav"

    logger.info(f"开始转换音频: {input_file}")

    # ffmpeg 命令参数说明：
    # -i: 输入文件
    # -ar: 设置采样率为 16000 Hz
    # -ac: 设置声道数为 1（mono）
    # -sample_fmt s16: 16-bit PCM
    # -y: 覆盖输出文件
    cmd = [
        "ffmpeg",
        "-i", str(input_file),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-sample_fmt", "s16",
        "-y",  # 覆盖已存在的文件
        str(output_file),
    ]

    run_command(cmd, timeout=300)  # 5分钟超时

    if not output_file.exists():
        raise CommandError(
            message=f"转换完成但文件不存在: {output_file}",
            returncode=-1,
            stderr="File not found after conversion",
        )

    logger.info(f"音频转换完成: {output_file}")
    return output_file


def preprocess_audio(
    file_path_or_url: str,
    task_id: str,
    is_url: bool = False,
) -> Path:
    """
    音频预处理入口函数

    根据输入类型（URL 或本地文件），进行相应的预处理，
    最终输出标准化的 WAV 文件。

    Args:
        file_path_or_url: 文件路径或 URL
        task_id: 任务 ID
        is_url: 是否为 URL

    Returns:
        Path: 预处理后的 WAV 文件路径
    """
    # 创建任务专属的临时目录
    temp_dir = settings.TEMP_DIR / task_id / "preprocess"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if is_url:
        # URL 模式：下载并转换
        wav_file = download_audio_from_url(file_path_or_url, temp_dir)
    else:
        # 本地文件模式：直接转换
        input_file = Path(file_path_or_url)
        if not input_file.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
        wav_file = convert_audio_to_wav(input_file, temp_dir)

    return wav_file
