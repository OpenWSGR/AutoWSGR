"""
EasyOCR 模型下载助手（支持 GitHub/Tencent/ModelScope 镜像）
GitHub 源：从官方地址自动下载 zip 并解压提取 .pth 文件。
Tencent 源：从腾讯云镜像下载模型文件，由 kuai 提供。
ModelScope 源：从 ModelScope 镜像下载模型文件，由 Ceceliachenen 提供。
"""

import hashlib
import importlib.util
import logging
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from typing import Any, ClassVar


class _ColorFormatter(logging.Formatter):
    """只输出消息，按级别着色"""

    _COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: '\033[36m',  # 青色
        logging.INFO: '\033[32m',  # 绿色
        logging.WARNING: '\033[33m',  # 黄色
        logging.ERROR: '\033[31m',  # 红色
    }
    _RESET: ClassVar[str] = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelno, '')
        return f'{color}{record.getMessage()}{self._RESET}'


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(_ColorFormatter())
logger.addHandler(_handler)

# -------------------- 常量 --------------------
MODEL_FILES = ['craft_mlt_25k.pth', 'zh_sim_g2.pth']

EXPECTED_MD5 = {
    'craft_mlt_25k.pth': '2f8227d2def4037cdb3b34389dcf9ec1',
    'zh_sim_g2.pth': 'b601ce7143293387d3ec4f41a66edc07',
}

# 按镜像名称索引的下载配置，与 YAML 中 ocr.mirror 枚举值对齐
MIRROR_CONFIG: dict[str, dict[str, Any]] = {
    'github': {
        'type': 'zip',
        'urls': {
            'craft_mlt_25k.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip',
            'zh_sim_g2.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip',
        },
    },
    'tencent': {
        'type': 'http',
        'base_url': 'https://easyocr.v.ekuai.tech/',
        'split': {
            'craft_mlt_25k.pth': 4,
        },
    },
    'modelscope': {
        'type': 'http',
        'base_url': 'https://modelscope.cn/models/Ceceliachenen/easyocr/resolve/master/',
    },
}

# CLI 交互用的镜像选项（小写后即为 MIRROR_CONFIG key）
MIRROR_OPTIONS: list[str] = ['ModelScope', 'Tencent', 'GitHub']


def ensure_model_dir() -> str:
    """返回 EasyOCR 模型目录路径，不存在则创建。"""
    model_dir = os.path.join(os.path.expanduser('~'), '.EasyOCR', 'model')
    os.makedirs(model_dir, exist_ok=True)
    return model_dir


def download_model_file(
    fname: str,
    mirror: str,
    dest: str,
    *,
    expected_md5: str | None = None,
) -> None:
    """根据镜像类型下载单个模型文件到指定路径。

    Parameters
    ----------
    fname:
        模型文件名，如 ``'craft_mlt_25k.pth'``。
    mirror:
        镜像名称: ``'github'`` / ``'tencent'`` / ``'modelscope'``。
    mtype:
        下载方式: ``'zip'``（下载后解压）/ ``'http'``（直连下载，支持分片）。
    dest:
        目标文件路径。
    expected_md5:
        若提供，下载后校验 MD5；不匹配时删除文件并抛出 ``RuntimeError``。
    """
    cfg = MIRROR_CONFIG[mirror]
    mtype = cfg['type']

    if mtype == 'zip':
        download_zip(cfg['urls'][fname], fname, dest)
    elif mtype == 'http':
        split_count = cfg.get('split', {}).get(fname)
        if split_count is not None:
            download_split(cfg['base_url'], fname, dest, parts=split_count)
        else:
            download_file(cfg['base_url'] + fname, dest)
    else:
        raise ValueError(f'未知下载方式: {mtype}')

    if expected_md5 is not None:
        real = md5(dest)
        if real != expected_md5:
            os.remove(dest)
            raise RuntimeError(f'{fname} MD5 校验失败: 期望 {expected_md5}, 实际 {real}')
        logger.info('校验 %s MD5: %s 正确', dest, real)


# -------------------- 工具函数 --------------------
def format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的字符串（KB/MB/GB）"""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


def format_speed(speed_bytes_per_sec: float) -> str:
    """将下载速度格式化为人类可读的字符串（KB/s 或 MB/s）"""
    if speed_bytes_per_sec < 1024 * 1024:
        return f'{speed_bytes_per_sec / 1024:.1f} KB/s'
    else:
        return f'{speed_bytes_per_sec / (1024 * 1024):.1f} MB/s'


def get_input(prompt: str, default: str = '0', choices: list[str] | None = None) -> str:
    while True:
        user_input = input(prompt).strip()
        if not user_input:
            user_input = default
        if choices is None or user_input in choices:
            return user_input
        logger.warning('无效输入，请从 %s 中选择。', choices)


def print_step(msg: str) -> None:
    logger.info('-' * 60)
    logger.info('>>> %s', msg)
    logger.info('-' * 60)


def download_file(url: str, dest: str) -> None:
    """通用文件下载（带进度、大小、速度）"""
    logger.info('下载: %s -> %s', url, dest)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f'不支持的 URL 协议: {parsed.scheme}')
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310
            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            block_size = 4096
            start_time = time.time()
            last_speed_time = start_time
            last_speed_bytes = 0
            current_speed = 0
            last_display_time = start_time

            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    current_time = time.time()

                    # Calculate speed every second
                    if current_time - last_speed_time >= 1.0:
                        time_interval = current_time - last_speed_time
                        current_speed = (downloaded - last_speed_bytes) / time_interval
                        last_speed_time = current_time
                        last_speed_bytes = downloaded

                    # Update display every 0.1 seconds or when download completes
                    if current_time - last_display_time >= 0.1 or (
                        total > 0 and downloaded >= total
                    ):
                        speed_str = format_speed(current_speed)
                        downloaded_str = format_size(downloaded)

                        if total > 0:
                            total_str = format_size(total)
                            pct = min(100, downloaded * 100 / total)
                            sys.stdout.write(
                                f'\r下载进度: {pct:.1f}% | '
                                f'{downloaded_str}/{total_str} | '
                                f'速度: {speed_str}'
                            )
                        else:
                            sys.stdout.write(f'\r已下载: {downloaded_str} | 速度: {speed_str}')
                        sys.stdout.flush()
                        last_display_time = current_time

            # Final newline and summary
            total_time = time.time() - start_time
            avg_speed = downloaded / total_time if total_time > 0 else 0
            sys.stdout.write('\n')
            logger.info(
                '下载完成: %s, 平均速度: %s',
                format_size(downloaded),
                format_speed(avg_speed),
            )
    except Exception as e:
        logger.error('下载失败: %s', e)
        raise


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            h.update(chunk)
    return h.hexdigest()


def check_model_file(path: str, fname: str) -> bool:
    """检查单个模型文件是否存在且 MD5 正确。"""
    if not os.path.isfile(path):
        return False
    return md5(path) == EXPECTED_MD5[fname]


def download_split(base_url: str, filename: str, dest: str, *, parts: int = 4) -> None:
    """分片下载并合并"""
    tmp_parts: list[str] = []
    logger.info('分片下载: %s (共 %d 部分)', filename, parts)
    try:
        for i in range(1, parts + 1):
            suffix = f'.part_{i:03d}'
            part_url = base_url + filename + suffix
            part_local = dest + suffix
            logger.info('[部分 %d/%d]', i, parts)
            download_file(part_url, part_local)
            tmp_parts.append(part_local)

        logger.info('合并分片...')
        with open(dest, 'wb') as out:
            for p in tmp_parts:
                with open(p, 'rb') as f:
                    data = f.read()
                    out.write(data)
                    logger.info(
                        '已合并: %s (%.2f MB)', os.path.basename(p), len(data) / 1024 / 1024
                    )
    finally:
        logger.info('清理临时分片...')
        for p in tmp_parts:
            if os.path.exists(p):
                os.remove(p)


def download_zip(zip_url: str, pth_name: str, dest_path: str) -> None:
    """下载 zip 文件并解压提取指定的 .pth 模型文件"""
    tmp_zip = dest_path + '.zip'
    try:
        download_file(zip_url, tmp_zip)

        logger.info('解压 %s ...', os.path.basename(tmp_zip))
        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            pth_files = [f for f in zf.namelist() if f.endswith('.pth')]
            if not pth_files:
                raise RuntimeError(f'压缩包中未找到任何 .pth 文件: {tmp_zip}')

            target = next((f for f in pth_files if os.path.basename(f) == pth_name), pth_files[0])
            logger.info('提取文件: %s', target)

            with zf.open(target) as src, open(dest_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
    logger.info('解压完成，模型文件保存为: %s', dest_path)


# -------------------- 主流程 --------------------
def check_easyocr() -> bool:
    """检测 EasyOCR 环境，返回是否已安装"""
    print_step('1. 检测 EasyOCR 环境')
    if importlib.util.find_spec('easyocr') is not None:
        logger.info('EasyOCR 已安装。')
        return True

    logger.warning('未检测到 EasyOCR')
    opt = get_input('[0] 跳过继续下载 (默认)  [1] 退出: ', '0', ['0', '1'])
    if opt == '1':
        sys.exit(0)
    logger.info('跳过安装，将继续下载模型。')
    return False


def prepare_model_dir() -> str:
    """准备模型目录并返回路径"""
    print_step('2. 准备模型目录')
    model_dir = ensure_model_dir()
    logger.info('目标: %s', model_dir)
    return model_dir


def select_mirror() -> str:
    """选择下载镜像源，返回镜像 key（如 'github' / 'tencent' / 'modelscope'）"""
    print_step('3. 选择下载镜像源')
    for i, name in enumerate(MIRROR_OPTIONS):
        logger.info('  [%d] %s', i, name)
    choice = get_input('请输入数字 (默认0): ', '0', [str(i) for i in range(len(MIRROR_OPTIONS))])
    return MIRROR_OPTIONS[int(choice)].lower()


def download_models(
    mirror: str,
    model_dir: str,
) -> None:
    """下载所有模型文件"""
    print_step('4. 下载模型文件')
    for fname in MODEL_FILES:
        logger.info('--- 处理: %s ---', fname)
        dst = os.path.join(model_dir, fname)

        if check_model_file(dst, fname):
            logger.info('已有文件校验通过，跳过下载: %s', dst)
            continue

        if os.path.exists(dst):
            logger.warning('已有文件 MD5 不匹配，将重新下载: %s', dst)

        tmp = os.path.join(model_dir, fname + '.tmp')
        try:
            download_model_file(fname, mirror, tmp, expected_md5=EXPECTED_MD5[fname])
        except Exception as e:
            logger.error('下载或解压失败: %s', e)
            sys.exit(1)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(tmp, dst)
        logger.info('已移动到 %s', dst)


def verify_loading() -> None:
    """验证 EasyOCR 模型加载"""
    print_step('5. 验证 EasyOCR 加载')
    try:
        import easyocr

        easyocr.Reader(['ch_sim', 'en'])
        logger.info('验证成功，模型可正常加载。')
    except Exception as e:
        logger.error('验证失败: %s', e)


def main() -> None:
    print_step('EasyOCR 模型下载助手')

    easyocr_ok = check_easyocr()
    model_dir = prepare_model_dir()
    mirror = select_mirror()
    download_models(mirror, model_dir)

    print_step('所有模型就绪')

    if easyocr_ok:
        verify_loading()
    else:
        print_step('5. 跳过验证 (EasyOCR 未安装)')

    logger.info('脚本完成。')


if __name__ == '__main__':
    main()
