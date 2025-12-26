"""
Basic Pitch 音高检测服务模块

使用 Spotify 的 Basic Pitch 模型进行音频转 MIDI：
- 自动音高检测（AMT - Automatic Music Transcription）
- 支持多音轨检测
- 输出标准 MIDI 文件

Basic Pitch 是一个基于深度学习的音高检测模型，
能够将音频信号转换为 MIDI 音符序列。
"""

import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def audio_to_midi(audio_file: Path, task_id: str) -> Path:
    """
    使用 Basic Pitch 将音频转换为 MIDI

    Args:
        audio_file: 输入音频文件（WAV 格式）
        task_id: 任务 ID

    Returns:
        Path: 生成的 MIDI 文件路径

    Raises:
        Exception: 转换失败时抛出
    """
    # 延迟导入，避免在模块加载时就加载 TensorFlow
    # Basic Pitch 依赖 TensorFlow，加载较慢
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    # 创建输出目录
    output_dir = settings.TEMP_DIR / task_id / "midi"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"开始音高检测: {audio_file}")

    # Basic Pitch predict_and_save 参数说明：
    # audio_path_list: 音频文件路径列表
    # output_directory: MIDI 输出目录
    # save_midi: 是否保存 MIDI 文件
    # sonify_midi: 是否生成音频预览（我们不需要）
    # save_model_outputs: 是否保存模型原始输出（我们不需要）
    # save_notes: 是否保存音符 CSV（我们不需要）
    #
    # 模型参数（可选调优）：
    # onset_threshold: 音符起始检测阈值 (0-1)，越低越敏感
    # frame_threshold: 帧检测阈值 (0-1)
    # minimum_note_length: 最小音符长度（秒）
    # minimum_frequency: 最低频率（Hz）
    # maximum_frequency: 最高频率（Hz）

    predict_and_save(
        audio_path_list=[str(audio_file)],
        output_directory=str(output_dir),
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        model_or_model_path=ICASSP_2022_MODEL_PATH,
        # 调优参数：适合乐器音乐
        onset_threshold=0.5,
        frame_threshold=0.3,
        minimum_note_length=0.05,  # 50ms 最小音符
        minimum_frequency=32.0,    # 约 C1
        maximum_frequency=4000.0,  # 约 B7
    )

    # Basic Pitch 输出文件名格式：{input_filename}_basic_pitch.mid
    input_stem = audio_file.stem
    midi_file = output_dir / f"{input_stem}_basic_pitch.mid"

    if not midi_file.exists():
        # 尝试查找任何 .mid 文件
        midi_files = list(output_dir.glob("*.mid"))
        if midi_files:
            midi_file = midi_files[0]
        else:
            raise FileNotFoundError(f"MIDI 文件未生成: {output_dir}")

    logger.info(f"音高检测完成: {midi_file}")
    return midi_file


def merge_midi_tracks(midi_files: list[Path], output_file: Path) -> Path:
    """
    合并多个 MIDI 文件（如果有多个音轨）

    Args:
        midi_files: MIDI 文件列表
        output_file: 输出文件路径

    Returns:
        Path: 合并后的 MIDI 文件路径
    """
    # 延迟导入
    from midiutil import MIDIFile
    import mido

    if len(midi_files) == 1:
        # 只有一个文件，直接复制
        import shutil
        shutil.copy(midi_files[0], output_file)
        return output_file

    # 使用 mido 合并多个 MIDI 文件
    merged = mido.MidiFile()

    for midi_path in midi_files:
        midi = mido.MidiFile(str(midi_path))
        for track in midi.tracks:
            merged.tracks.append(track)

    merged.save(str(output_file))
    logger.info(f"MIDI 文件合并完成: {output_file}")
    return output_file
