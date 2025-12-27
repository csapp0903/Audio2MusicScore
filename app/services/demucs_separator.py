"""
Demucs 音源分离服务模块

使用 Demucs 模型将混合音频分离为独立的音轨：
- drums: 鼓/打击乐
- bass: 贝斯
- other: 其他乐器（通常包含钢琴、吉他等）
- vocals: 人声

对于乐谱转换，我们主要关注 'other' 或 'vocals' 音轨。
"""

import logging
from pathlib import Path

from app.core.config import settings
from app.core.utils import run_command, CommandError

logger = logging.getLogger(__name__)

# Demucs 模型选择
# htdemucs: 默认模型，平衡速度和质量
# htdemucs_ft: 精调版本，质量更好但更慢
DEFAULT_MODEL = "htdemucs"

# 需要保留的音轨（用于后续转换）
# 'other' 通常包含旋律乐器如钢琴、吉他
# 'vocals' 用于提取人声旋律
TARGET_STEMS = ["other", "vocals"]


def separate_audio(wav_file: Path, task_id: str) -> dict[str, Path]:
    """
    使用 Demucs 分离音频源

    将输入的混合音频分离为多个独立音轨，
    返回目标音轨的文件路径。

    Args:
        wav_file: 预处理后的 WAV 文件
        task_id: 任务 ID

    Returns:
        dict[str, Path]: 音轨名称到文件路径的映射
            例如: {"other": Path(...), "vocals": Path(...)}

    Raises:
        CommandError: Demucs 执行失败时抛出
    """
    # 创建 Demucs 输出目录
    output_dir = settings.TEMP_DIR / task_id / "demucs"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"开始音源分离: {wav_file}")

    # Demucs 命令参数说明：
    # -n: 模型名称
    # -o: 输出目录
    # --two-stems: 可选，只分离为两个音轨（如 vocals/accompaniment）
    # --mp3: 输出为 mp3 格式（节省空间，但我们需要 wav）
    # 不使用 --mp3，保持 wav 格式以确保质量
    cmd = [
        "demucs",
        "-n", DEFAULT_MODEL,
        "-o", str(output_dir),
        "--filename", "{track}/{stem}.{ext}",
        str(wav_file),
    ]

    # Demucs 处理可能需要较长时间（取决于音频长度和 GPU）
    run_command(cmd, timeout=1200)  # 20分钟超时

    # Demucs 输出目录结构：
    # {output_dir}/{model_name}/{input_filename_without_ext}/{stem}.wav
    # 例如: temp/task_id/demucs/htdemucs/converted/drums.wav

    # 查找分离后的文件
    model_output_dir = output_dir / DEFAULT_MODEL

    # 找到实际的输出子目录（以输入文件名命名）
    subdirs = list(model_output_dir.iterdir()) if model_output_dir.exists() else []
    if not subdirs:
        raise CommandError(
            message="Demucs 输出目录为空",
            returncode=-1,
            stderr=f"No output found in {model_output_dir}",
        )

    stem_dir = subdirs[0]  # 通常只有一个子目录

    # 收集目标音轨
    stems = {}
    for stem_name in TARGET_STEMS:
        stem_file = stem_dir / f"{stem_name}.wav"
        if stem_file.exists():
            stems[stem_name] = stem_file
            logger.info(f"找到音轨: {stem_name} -> {stem_file}")
        else:
            logger.warning(f"音轨不存在: {stem_name}")

    if not stems:
        raise CommandError(
            message="未找到任何目标音轨",
            returncode=-1,
            stderr=f"No target stems found in {stem_dir}",
        )

    logger.info(f"音源分离完成，共 {len(stems)} 个音轨")
    return stems


def get_primary_stem(stems: dict[str, Path]) -> Path:
    """
    获取主要音轨用于后续处理

    优先级：other > vocals

    Args:
        stems: 音轨字典

    Returns:
        Path: 主要音轨文件路径
    """
    # 优先使用 'other'（通常包含乐器旋律）
    if "other" in stems:
        return stems["other"]
    # 备选使用 'vocals'
    if "vocals" in stems:
        return stems["vocals"]
    # 返回任意可用的音轨
    return next(iter(stems.values()))
