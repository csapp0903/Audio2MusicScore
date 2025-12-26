"""
音频处理 Celery 任务模块

这是音频转乐谱系统的核心处理流程，包含以下步骤：
1. 预处理：下载/转换音频为标准 WAV 格式
2. 分离：使用 Demucs 提取乐器音轨
3. 识别：使用 Basic Pitch 转换为 MIDI
4. 转换：使用 Music21 + MuseScore 生成乐谱
5. 清理：整理结果文件，删除临时文件
"""

import logging
import shutil
from pathlib import Path

from celery import states

from app.core.config import settings
from app.core.utils import CommandError
from app.tasks.celery_app import celery_app

# 服务模块（处理各个阶段）
from app.services.audio_preprocessor import preprocess_audio
from app.services.demucs_separator import separate_audio, get_primary_stem
from app.services.pitch_detector import audio_to_midi
from app.services.score_converter import convert_to_score

logger = logging.getLogger(__name__)


def update_task_progress(task, step: str, progress: int = 0):
    """
    更新任务进度状态

    Args:
        task: Celery 任务实例
        step: 当前步骤描述
        progress: 进度百分比 (0-100)
    """
    task.update_state(
        state="PROGRESS",
        meta={
            "step": step,
            "progress": progress,
        }
    )
    logger.info(f"任务进度: {step} ({progress}%)")


def cleanup_temp_files(task_id: str):
    """
    清理任务的临时文件

    Args:
        task_id: 任务 ID
    """
    temp_dir = settings.TEMP_DIR / task_id
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {e}")


def move_results_to_final(task_id: str, score_files: dict[str, Path]) -> dict[str, str]:
    """
    将生成的乐谱文件移动到最终结果目录

    Args:
        task_id: 任务 ID
        score_files: 包含 musicxml 和 pdf 路径的字典

    Returns:
        dict[str, str]: 最终文件路径（字符串格式）
    """
    result_dir = settings.RESULT_DIR / task_id
    result_dir.mkdir(parents=True, exist_ok=True)

    final_files = {}

    for file_type, src_path in score_files.items():
        if src_path and src_path.exists():
            # 确定目标文件名
            dst_path = result_dir / f"score.{file_type}"
            if file_type == "musicxml":
                dst_path = result_dir / "score.musicxml"
            elif file_type == "pdf":
                dst_path = result_dir / "score.pdf"

            # 移动文件
            shutil.copy2(src_path, dst_path)
            final_files[file_type] = str(dst_path)
            logger.info(f"结果文件: {file_type} -> {dst_path}")

    return final_files


@celery_app.task(bind=True, name="process_audio_task")
def process_audio_task(
    self,
    task_id: str,
    file_path_or_url: str,
    is_url: bool = False,
) -> dict:
    """
    音频转乐谱主任务

    完整处理流程：
    1. 预处理 -> 标准化 WAV (16kHz, mono)
    2. 分离 -> Demucs 提取乐器音轨
    3. 识别 -> Basic Pitch 转 MIDI
    4. 转换 -> Music21 + MuseScore 生成乐谱
    5. 清理 -> 整理结果，删除临时文件

    Args:
        task_id: 任务唯一标识
        file_path_or_url: 文件路径或 URL
        is_url: 是否为 URL 输入

    Returns:
        dict: 包含任务结果的字典
            - task_id: 任务 ID
            - status: 状态
            - files: 结果文件路径
    """
    try:
        logger.info(f"{'='*50}")
        logger.info(f"开始处理任务: {task_id}")
        logger.info(f"输入: {file_path_or_url}")
        logger.info(f"类型: {'URL' if is_url else '文件'}")
        logger.info(f"{'='*50}")

        # ============================================================
        # Step 1: 预处理 - 下载/转换音频
        # ============================================================
        update_task_progress(self, "预处理音频", 10)

        wav_file = preprocess_audio(
            file_path_or_url=file_path_or_url,
            task_id=task_id,
            is_url=is_url,
        )
        logger.info(f"预处理完成: {wav_file}")

        # ============================================================
        # Step 2: 音源分离 - Demucs
        # ============================================================
        update_task_progress(self, "音源分离 (Demucs)", 30)

        stems = separate_audio(wav_file, task_id)
        primary_stem = get_primary_stem(stems)
        logger.info(f"音源分离完成，主音轨: {primary_stem}")

        # ============================================================
        # Step 3: 音高检测 - Basic Pitch
        # ============================================================
        update_task_progress(self, "音高检测 (Basic Pitch)", 50)

        midi_file = audio_to_midi(primary_stem, task_id)
        logger.info(f"MIDI 生成完成: {midi_file}")

        # ============================================================
        # Step 4: 乐谱转换 - Music21 + MuseScore
        # ============================================================
        update_task_progress(self, "生成乐谱 (Music21 + MuseScore)", 70)

        score_files = convert_to_score(midi_file, task_id)
        logger.info(f"乐谱生成完成: {score_files}")

        # ============================================================
        # Step 5: 整理结果
        # ============================================================
        update_task_progress(self, "整理结果文件", 90)

        # 将结果文件移动到最终目录
        final_files = move_results_to_final(task_id, score_files)

        # 同时保存 MIDI 文件到结果目录
        midi_result = settings.RESULT_DIR / task_id / "score.mid"
        shutil.copy2(midi_file, midi_result)
        final_files["midi"] = str(midi_result)

        # ============================================================
        # Step 6: 清理临时文件
        # ============================================================
        update_task_progress(self, "清理临时文件", 95)
        cleanup_temp_files(task_id)

        # ============================================================
        # 完成
        # ============================================================
        update_task_progress(self, "完成", 100)

        result = {
            "task_id": task_id,
            "status": "SUCCESS",
            "files": final_files,
            "download_urls": {
                file_type: f"/download/{task_id}/score.{file_type}"
                for file_type in final_files.keys()
            },
        }

        logger.info(f"{'='*50}")
        logger.info(f"任务完成: {task_id}")
        logger.info(f"结果: {result}")
        logger.info(f"{'='*50}")

        return result

    except CommandError as e:
        # 命令执行错误（ffmpeg, demucs, musescore 等）
        logger.exception(f"命令执行失败: {task_id}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "error": e.message,
                "stderr": e.stderr,
                "step": "命令执行",
            },
        )
        # 清理临时文件
        cleanup_temp_files(task_id)
        raise

    except FileNotFoundError as e:
        # 文件未找到错误
        logger.exception(f"文件未找到: {task_id}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "error": str(e),
                "step": "文件处理",
            },
        )
        cleanup_temp_files(task_id)
        raise

    except Exception as e:
        # 其他未知错误
        logger.exception(f"任务失败: {task_id}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "error": str(e),
                "step": "未知",
            },
        )
        cleanup_temp_files(task_id)
        raise
