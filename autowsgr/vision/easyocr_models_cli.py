"""
EasyOCR 模型下载助手（支持 GitHub/EdgeOne/ModelScope 镜像）
GitHub 源：从官方地址自动下载 zip 并解压提取 .pth 文件。
EdgeOne 源：从 EdgeOne 镜像下载模型文件，由 kuai 提供。
ModelScope 源：从 ModelScope 镜像下载模型文件，由 Ceceliachenen 提供。
"""

import hashlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
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
        'type': 'github',
        'urls': {
            'craft_mlt_25k.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip',
            'zh_sim_g2.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip',
        },
    },
    'tencent': {
        'type': 'edgeone',
        'base_url': 'https://easyocr.v.ekuai.tech/',
        'split': {
            'craft_mlt_25k.pth': 4,
        },
    },
    'modelscope': {
        'type': 'modelscope',
    },
}

# CLI 交互用的镜像选项（引用 MIRROR_CONFIG 避免重复声明 URL）
MIRROR_OPTIONS: dict[str, dict[str, Any]] = {
    '0': {
        'name': 'GitHub',
        'key': 'github',
    },
    '1': {
        'name': 'EdgeOne (腾讯云)',
        'key': 'tencent',
    },
    '2': {
        'name': 'ModelScope',
        'key': 'modelscope',
    },
}

MODELSCOPE_MODEL = 'Ceceliachenen/easyocr'


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
    dest:
        目标文件路径。
    expected_md5:
        若提供，下载后校验 MD5；不匹配时删除文件并抛出 ``RuntimeError``。
    """
    cfg = MIRROR_CONFIG[mirror]
    mtype = cfg['type']

    if mtype == 'github':
        download_github_zip(cfg['urls'][fname], fname, dest)
    elif mtype == 'edgeone':
        split_count = cfg.get('split', {}).get(fname)
        if split_count is not None:
            download_edgeone_split(cfg['base_url'], fname, dest, parts=split_count)
        else:
            download_file(cfg['base_url'] + fname, dest)
    elif mtype == 'modelscope':
        dest_dir = os.path.dirname(dest) or '.'
        download_modelscope(fname, dest_dir)
        # modelscope API 直接写入 local_dir，若目标路径不同则移动
        src = os.path.join(dest_dir, fname)
        if src != dest and os.path.exists(src):
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(src, dest)
    else:
        raise ValueError(f'未知下载方式: {mtype}')

    if expected_md5 is not None:
        real = md5(dest)
        if real != expected_md5:
            os.remove(dest)
            raise RuntimeError(f'{fname} MD5 校验失败: 期望 {expected_md5}, 实际 {real}')
        logger.info('校验 %s MD5: %s 正确', dest, real)


# -------------------- 工具函数 --------------------
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
    """通用文件下载（带进度）"""
    logger.info('下载: %s -> %s', url, dest)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f'不支持的 URL 协议: {parsed.scheme}')
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310
            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            block_size = 4096

            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        pct = min(100, downloaded * 100 / total)
                        sys.stdout.write(f'\r下载进度: {pct:.1f}%')
                        sys.stdout.flush()

            if total > 0:
                sys.stdout.write('\n')
        logger.info('下载完成')
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


def download_modelscope(filename: str, local_dir: str = '.') -> None:
    """使用 ModelScope Python API 下载单个文件"""
    try:
        from modelscope.hub.file_download import model_file_download
    except ImportError as err:
        raise RuntimeError('modelscope 安装不完整，缺少 hub.file_download 模块') from err
    logger.info('ModelScope API 下载: %s -> %s', filename, local_dir)
    model_file_download(
        model_id=MODELSCOPE_MODEL,
        file_path=filename,
        local_dir=local_dir,
    )
    logger.info('下载完成')


def download_edgeone_split(base_url: str, filename: str, dest: str, *, parts: int = 4) -> None:
    """EdgeOne 分片下载并合并"""
    tmp_parts: list[str] = []
    logger.info('EdgeOne 分片下载: %s (共 %d 部分)', filename, parts)
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


def download_github_zip(zip_url: str, pth_name: str, dest_path: str) -> None:
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
    for k, v in MIRROR_OPTIONS.items():
        logger.info('  [%s] %s', k, v['name'])
    choice = get_input('请输入数字 (默认0): ', '0', ['0', '1', '2'])
    mirror_key = MIRROR_OPTIONS[choice]['key']

    if mirror_key == 'modelscope':
        _ensure_modelscope_interactive()

    return mirror_key


def ensure_modelscope() -> None:
    """确保 modelscope 已安装，未安装时静默自动安装。"""
    if importlib.util.find_spec('modelscope') is not None:
        return
    logger.info('安装 modelscope ...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'modelscope'])
    logger.info('modelscope 安装成功')


def _ensure_modelscope_interactive() -> None:
    """CLI 交互模式：确认后安装 modelscope。"""
    if importlib.util.find_spec('modelscope') is not None:
        logger.info('modelscope 已安装。')
        return

    logger.warning('未安装 modelscope')
    ins = get_input('自动安装? [0] 是 (默认)  [1] 否: ', '0', ['0', '1'])
    if ins == '0':
        ensure_modelscope()
    else:
        logger.warning('请手动安装 modelscope 后重试。')
        sys.exit(0)


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
