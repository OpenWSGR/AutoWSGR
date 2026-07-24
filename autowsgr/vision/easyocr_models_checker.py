"""EasyOCR 模型管理 — 检查、校验、下载。

在运行时初始化 EasyOCR 前调用 :func:`ensure_models`，自动完成：
1. 检查模型目录中是否存在所需模型文件
2. 校验 MD5
3. 若缺失或损坏，从用户配置的镜像源下载
"""

from __future__ import annotations

import os
import shutil

from autowsgr.infra.logger import get_logger

# 从 CLI 模块导入共享常量和下载函数（单一维护点）
from .easyocr_models_cli import (
    EXPECTED_MD5,
    MODEL_FILES,
    check_model_file,
    download_model_file,
    ensure_model_dir,
    ensure_modelscope,
)


_log = get_logger('vision.model_download')


def ensure_models(mirror: str = 'tencent') -> None:
    """确保所有 EasyOCR 模型就绪。

    Parameters
    ----------
    mirror:
        镜像源名称: ``'origin'`` / ``'github'`` / ``'tencent'`` / ``'modelscope'``。
        为 ``'origin'`` 时不执行任何检查或下载，由 EasyOCR 自行处理。
    """
    model_dir = ensure_model_dir()

    if mirror == 'origin':
        return

    if mirror == 'modelscope':
        ensure_modelscope()

    for fname in MODEL_FILES:
        path = os.path.join(model_dir, fname)
        if check_model_file(path, fname):
            _log.info('[Model] {} 已就绪', fname)
            continue

        if os.path.isfile(path):
            _log.warning('[Model] {} MD5 不匹配，将重新下载', fname)

        _log.info('[Model] 从镜像源 {} 下载EasyOCR模型 {}', mirror, path)
        _download_and_verify(fname, mirror, model_dir, path)


def _download_and_verify(fname: str, mirror: str, model_dir: str, dest: str) -> None:
    """下载单个模型文件到临时位置，校验后移入模型目录。"""
    tmp = os.path.join(model_dir, fname + '.tmp')
    # 清理可能残留的临时文件
    if os.path.exists(tmp):
        os.remove(tmp)
    try:
        download_model_file(fname, mirror, tmp, expected_md5=EXPECTED_MD5[fname])
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(tmp, dest)
        _log.info('[Model] {} 下载完成并校验通过', fname)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
