"""
工具函数模块

提供通用的辅助函数，如命令执行、文件操作等。
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandError(Exception):
    """命令执行异常"""

    def __init__(self, message: str, returncode: int, stderr: str):
        self.message = message
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(self.message)


def run_command(
    cmd_list: list[str],
    cwd: Path | str | None = None,
    timeout: int | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    封装 subprocess.run，执行外部命令并处理错误。

    Args:
        cmd_list: 命令及参数列表，例如 ["ls", "-la"]
        cwd: 工作目录
        timeout: 超时时间（秒）
        capture_output: 是否捕获输出

    Returns:
        subprocess.CompletedProcess: 命令执行结果

    Raises:
        CommandError: 命令执行失败时抛出
    """
    cmd_str = " ".join(cmd_list)
    logger.info(f"执行命令: {cmd_str}")

    try:
        result = subprocess.run(
            cmd_list,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"命令执行失败: {cmd_str}")
            logger.error(f"返回码: {result.returncode}")
            logger.error(f"错误输出: {result.stderr}")
            raise CommandError(
                message=f"命令执行失败: {cmd_str}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        logger.debug(f"命令执行成功: {cmd_str}")
        if result.stdout:
            logger.debug(f"标准输出: {result.stdout[:500]}")

        return result

    except subprocess.TimeoutExpired as e:
        logger.error(f"命令执行超时: {cmd_str}")
        raise CommandError(
            message=f"命令执行超时 ({timeout}秒): {cmd_str}",
            returncode=-1,
            stderr=str(e),
        )
    except FileNotFoundError as e:
        logger.error(f"命令未找到: {cmd_list[0]}")
        raise CommandError(
            message=f"命令未找到: {cmd_list[0]}",
            returncode=-1,
            stderr=str(e),
        )


def run_with_xvfb(cmd_list: list[str], **kwargs) -> subprocess.CompletedProcess:
    """
    使用 xvfb-run 执行需要图形环境的命令（如 MuseScore）。

    Args:
        cmd_list: 命令及参数列表
        **kwargs: 传递给 run_command 的其他参数

    Returns:
        subprocess.CompletedProcess: 命令执行结果
    """
    xvfb_cmd = ["xvfb-run", "-a", "--server-args=-screen 0 1024x768x24"] + cmd_list
    return run_command(xvfb_cmd, **kwargs)


def safe_filename(filename: str) -> str:
    """
    清理文件名，移除不安全字符。

    Args:
        filename: 原始文件名

    Returns:
        str: 安全的文件名
    """
    # 保留字母、数字、下划线、连字符和点
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    return "".join(c if c in safe_chars else "_" for c in filename)
