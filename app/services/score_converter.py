"""
乐谱转换服务模块

使用 Music21 和 MuseScore 进行乐谱转换：
1. Music21: MIDI -> MusicXML（包含量化处理）
2. MuseScore: MusicXML -> PDF（需要 xvfb-run）

Music21 是一个功能强大的音乐学分析库，
可以处理各种音乐格式并进行乐理分析。
"""

import logging
from pathlib import Path

from app.core.config import settings
from app.core.utils import run_command, CommandError

logger = logging.getLogger(__name__)


def midi_to_musicxml(midi_file: Path, task_id: str) -> Path:
    """
    使用 Music21 将 MIDI 转换为 MusicXML

    处理步骤：
    1. 加载 MIDI 文件
    2. 量化（Quantize）音符到标准节拍
    3. 分析并添加调号、拍号
    4. 导出为 MusicXML 格式

    Args:
        midi_file: MIDI 文件路径
        task_id: 任务 ID

    Returns:
        Path: 生成的 MusicXML 文件路径

    Raises:
        Exception: 转换失败时抛出
    """
    # 延迟导入 music21（加载较慢）
    import music21
    from music21 import converter, instrument, stream, meter, key

    # 创建输出目录
    output_dir = settings.TEMP_DIR / task_id / "score"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "score.musicxml"

    logger.info(f"开始 MIDI 转 MusicXML: {midi_file}")

    # 1. 加载 MIDI 文件
    # Music21 自动解析 MIDI 并创建 Stream 对象
    score = converter.parse(str(midi_file))

    # 2. 量化处理（Quantize）
    # 将音符时值对齐到标准节拍网格（如八分音符、十六分音符）
    # 这对于生成可读的乐谱非常重要
    #
    # quarterLengthDivisors: 定义量化精度
    # [8, 6, 4, 3] 表示支持：
    # - 8: 三十二分音符 (1/8 of quarter note)
    # - 6: 六连音 (sextuplets)
    # - 4: 十六分音符 (1/4 of quarter note)
    # - 3: 三连音 (triplets)
    score.quantize(
        quarterLengthDivisors=[8, 6, 4, 3],
        processOffsets=True,   # 量化音符起始位置
        processDurations=True  # 量化音符时值
    )

    # 3. 分析调号（可选，如果 MIDI 中没有）
    # 使用 music21 的调性分析算法
    try:
        analyzed_key = score.analyze('key')
        if analyzed_key:
            logger.info(f"检测到调号: {analyzed_key}")
            # 如果乐谱没有调号，添加分析结果
            for part in score.parts:
                # 正确检查是否已存在调号：getElementsByClass 返回 Stream，需要检查长度
                existing_keys = list(part.recurse().getElementsByClass(key.Key))
                if not existing_keys:
                    # 创建调号的副本以避免重复引用问题
                    new_key = key.Key(analyzed_key.tonic, analyzed_key.mode)
                    part.insert(0, new_key)
    except Exception as e:
        logger.warning(f"调号分析失败: {e}")

    # 4. 确保有拍号
    # 如果 MIDI 没有拍号信息，默认使用 4/4
    has_time_sig = bool(score.flatten().getElementsByClass(meter.TimeSignature))
    if not has_time_sig:
        logger.info("未检测到拍号，使用默认 4/4")
        for part in score.parts:
            part.insert(0, meter.TimeSignature('4/4'))

    # 5. 添加乐器信息（如果缺失）
    for part in score.parts:
        # 移除所有复杂的乐器定义
        # 使用 recurse() 遍历所有层级，收集要删除的元素
        instruments_to_remove = list(part.recurse().getElementsByClass(instrument.Instrument))
        for inst in instruments_to_remove:
            # 安全地从其所在容器中移除
            try:
                inst.activeSite.remove(inst)
            except Exception:
                # 如果移除失败，尝试从 part 递归移除
                try:
                    part.remove(inst, recurse=True)
                except Exception:
                    pass  # 忽略移除失败的情况

        # 在开头插入一个标准的钢琴乐器
        part.insert(0, instrument.Piano())
    # 6. 导出为 MusicXML
    # Music21 支持多种导出格式：musicxml, midi, lily (LilyPond), etc.
    score.write('musicxml', fp=str(output_file))

    if not output_file.exists():
        raise FileNotFoundError(f"MusicXML 文件未生成: {output_file}")

    logger.info(f"MusicXML 生成完成: {output_file}")
    return output_file


def musicxml_to_pdf(musicxml_file: Path, task_id: str) -> Path:
    """
    使用 MuseScore 将 MusicXML 转换为 PDF

    MuseScore 是专业的乐谱排版软件，可以生成高质量的 PDF 乐谱。
    在无头服务器上运行需要使用 xvfb-run 提供虚拟显示器。

    Args:
        musicxml_file: MusicXML 文件路径
        task_id: 任务 ID

    Returns:
        Path: 生成的 PDF 文件路径

    Raises:
        CommandError: MuseScore 执行失败时抛出
    """
    # 创建输出目录
    output_dir = settings.TEMP_DIR / task_id / "score"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "score.pdf"

    logger.info(f"开始 MusicXML 转 PDF: {musicxml_file}")

    # 构建 MuseScore 命令
    # MuseScore 命令行参数：
    # -o: 输出文件路径（根据扩展名自动判断格式）
    # 支持的输出格式：pdf, png, svg, mp3, wav, midi, musicxml, etc.

    musescore_cmd = [
        settings.MUSESCORE_PATH,
        str(musicxml_file),
        "-o", str(output_file),
    ]

    # 在无头服务器上，MuseScore 需要图形环境
    # 使用 xvfb-run 创建虚拟 X 服务器
    if settings.USE_XVFB:
        # xvfb-run 参数说明：
        # -a: 自动选择可用的显示器编号
        # --server-args: X 服务器参数
        #   -screen 0 1024x768x24: 创建 1024x768 分辨率，24位色深的虚拟屏幕
        cmd = [
            "xvfb-run",
            "-a",
            "--server-args=-screen 0 1024x768x24",
        ] + musescore_cmd
    else:
        cmd = musescore_cmd

    # 执行转换
    # MuseScore 转换通常很快，但复杂乐谱可能需要更长时间
    run_command(cmd, timeout=300)  # 5分钟超时

    if not output_file.exists():
        raise CommandError(
            message=f"PDF 文件未生成: {output_file}",
            returncode=-1,
            stderr="PDF file not found after conversion",
        )

    logger.info(f"PDF 生成完成: {output_file}")
    return output_file


def convert_to_score(midi_file: Path, task_id: str) -> dict[str, Path]:
    """
    乐谱转换入口函数

    将 MIDI 文件转换为 MusicXML 和 PDF 格式。

    Args:
        midi_file: MIDI 文件路径
        task_id: 任务 ID

    Returns:
        dict[str, Path]: 包含生成文件路径的字典
            - musicxml: MusicXML 文件路径
            - pdf: PDF 文件路径
    """
    # Step 1: MIDI -> MusicXML
    musicxml_file = midi_to_musicxml(midi_file, task_id)

    # Step 2: MusicXML -> PDF
    pdf_file = musicxml_to_pdf(musicxml_file, task_id)

    return {
        "musicxml": musicxml_file,
        "pdf": pdf_file,
    }
