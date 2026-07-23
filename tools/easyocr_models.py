"""
EasyOCR 模型下载助手（支持 GitHub/EdgeOne/ModelScope 镜像）
GitHub 源：从官方地址自动下载 zip 并解压提取 .pth 文件。
EdgeOne 源：从 EdgeOne 镜像下载模型文件，由 kuai 提供。
ModelScope 源：从 ModelScope 镜像下载模型文件，由 Ceceliachenen 提供。
"""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from typing import Any


# -------------------- 常量 --------------------
MODEL_FILES = ['craft_mlt_25k.pth', 'zh_sim_g2.pth']

EXPECTED_MD5 = {
    'craft_mlt_25k.pth': '2f8227d2def4037cdb3b34389dcf9ec1',
    'zh_sim_g2.pth': 'b601ce7143293387d3ec4f41a66edc07',
}

MIRROR_OPTIONS: dict[str, dict[str, Any]] = {
    '0': {
        'name': 'GitHub',
        'type': 'github',
        'urls': {
            'craft_mlt_25k.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip',
            'zh_sim_g2.pth': 'https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip',
        },
    },
    '1': {
        'name': 'EdgeOne',
        'base_url': 'http://easyocr.v.ekuai.tech/',
        'type': 'direct',
    },
    '2': {
        'name': 'ModelScope',
        'type': 'modelscope',
    },
}

MODELSCOPE_MODEL = 'Ceceliachenen/easyocr'


# -------------------- 工具函数 --------------------
def get_input(prompt: str, default: str = '0', choices: list[str] | None = None) -> str:
    while True:
        user_input = input(prompt).strip()
        if not user_input:
            user_input = default
        if choices is None or user_input in choices:
            return user_input
        print(f'无效输入，请从 {choices} 中选择。')


def print_step(msg: str) -> None:
    print(f'\n{"-" * 60}\n>>> {msg}\n{"-" * 60}')


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    print(f'目录已就绪: {path}' if os.path.isdir(path) else f'已创建目录: {path}')


def _download_hook(count: int, blk: int, total: int) -> None:
    if total > 0:
        pct = min(100, count * blk * 100 / total)
        sys.stdout.write(f'\r下载进度: {pct:.1f}%')
        sys.stdout.flush()
        if pct >= 100:
            sys.stdout.write('\n')


def download_file(url: str, dest: str) -> None:
    """通用文件下载（带进度）"""
    print(f'下载: {url} -> {dest}')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f'不支持的 URL 协议: {parsed.scheme}')
    try:
        urllib.request.urlretrieve(url, dest, _download_hook)  # noqa: S310
        print('下载完成')
    except Exception as e:
        print(f'下载失败: {e}')
        raise


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            h.update(chunk)
    return h.hexdigest()


def download_modelscope(filename: str, local_dir: str = '.') -> None:
    """使用 ModelScope Python API 下载单个文件"""
    try:
        from modelscope.hub.file_download import model_file_download
    except ImportError as err:
        raise RuntimeError('modelscope 安装不完整，缺少 hub.file_download 模块') from err
    print(f'ModelScope API 下载: {filename} -> {local_dir}')
    model_file_download(
        model_id=MODELSCOPE_MODEL,
        file_path=filename,
        local_dir=local_dir,
    )
    print('下载完成')


def download_edgeone_split(base_url: str, filename: str, dest: str) -> None:
    """EdgeOne 分片下载并合并"""
    parts = 4
    tmp_parts: list[str] = []
    print(f'EdgeOne 分片下载: {filename} (共 {parts} 部分)')
    for i in range(1, parts + 1):
        suffix = f'.part_{i:03d}'
        part_url = base_url + filename + suffix
        part_local = os.path.join(os.getcwd(), filename + suffix)
        print(f'\n[部分 {i}/{parts}]')
        download_file(part_url, part_local)
        tmp_parts.append(part_local)

    print('\n合并分片...')
    with open(dest, 'wb') as out:
        for p in tmp_parts:
            with open(p, 'rb') as f:
                data = f.read()
                out.write(data)
                print(f'已合并: {os.path.basename(p)} ({len(data) / 1024 / 1024:.2f} MB)')
    print('合并完成，删除临时分片...')
    for p in tmp_parts:
        os.remove(p)


def download_github_zip(zip_url: str, pth_name: str, dest_path: str) -> None:
    """下载 zip 文件并解压提取指定的 .pth 模型文件"""
    tmp_zip = os.path.join(os.getcwd(), pth_name + '.zip')
    download_file(zip_url, tmp_zip)

    print(f'解压 {os.path.basename(tmp_zip)} ...')
    with zipfile.ZipFile(tmp_zip, 'r') as zf:
        pth_files = [f for f in zf.namelist() if f.endswith('.pth')]
        if not pth_files:
            os.remove(tmp_zip)
            raise RuntimeError(f'压缩包中未找到任何 .pth 文件: {tmp_zip}')

        target = _find_pth_target(pth_files, pth_name)
        print(f'提取文件: {target}')

        with zf.open(target) as src, open(dest_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)

    os.remove(tmp_zip)
    print(f'解压完成，模型文件保存为: {dest_path}')


def _find_pth_target(pth_files: list[str], pth_name: str) -> str:
    """在 zip 文件列表中查找匹配的 .pth 文件"""
    for f in pth_files:
        if os.path.basename(f) == pth_name:
            return f
    return pth_files[0]


# -------------------- 主流程 --------------------
def check_easyocr() -> bool:
    """检测 EasyOCR 环境，返回是否已安装"""
    print_step('1. 检测 EasyOCR 环境')
    if importlib.util.find_spec('easyocr') is not None:
        print('EasyOCR 已安装。')
        return True

    print('未检测到 EasyOCR')
    opt = get_input('[0] 跳过继续下载 (默认)  [1] 退出: ', '0', ['0', '1'])
    if opt == '1':
        sys.exit(0)
    print('跳过安装，将继续下载模型。')
    return False


def prepare_model_dir() -> str:
    """准备模型目录并返回路径"""
    print_step('2. 准备模型目录')
    model_dir = os.path.join(os.path.expanduser('~'), '.EasyOCR', 'model')
    print(f'目标: {model_dir}')
    ensure_dir(model_dir)
    return model_dir


def select_mirror() -> tuple[str, dict[str, Any]]:
    """选择下载镜像源，返回 (choice, mirror)"""
    print_step('3. 选择下载镜像源')
    for k, v in MIRROR_OPTIONS.items():
        print(f'  [{k}] {v["name"]}')
    choice = get_input('请输入数字 (默认0): ', '0', ['0', '1', '2'])
    mirror = MIRROR_OPTIONS[choice]

    if choice == '2':
        _ensure_modelscope()

    return choice, mirror


def _ensure_modelscope() -> None:
    """确保 modelscope 已安装"""
    if importlib.util.find_spec('modelscope') is not None:
        print('modelscope 已安装。')
        return

    print('未安装 modelscope')
    ins = get_input('自动安装? [0] 是 (默认)  [1] 否: ', '0', ['0', '1'])
    if ins == '0':
        print('安装 modelscope ...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'modelscope'])
        print('安装成功')
    else:
        print('请手动安装 modelscope 后重试。')
        sys.exit(0)


def _download_one(fname: str, choice: str, mirror: dict[str, Any], tmp: str) -> None:
    """下载单个模型文件"""
    try:
        if mirror['type'] == 'github':
            download_github_zip(mirror['urls'][fname], fname, tmp)
        elif choice == '1' and fname == 'craft_mlt_25k.pth':
            download_edgeone_split(mirror['base_url'], fname, tmp)
        elif mirror['type'] == 'direct':
            download_file(mirror['base_url'] + fname, tmp)
        elif mirror['type'] == 'modelscope':
            download_modelscope(fname, os.getcwd())
        else:
            print(f'未知下载方式: {mirror["type"]}')
            sys.exit(1)
    except Exception as e:
        print(f'下载或解压失败: {e}')
        sys.exit(1)


def _verify_md5(fname: str, tmp: str) -> None:
    """校验文件 MD5"""
    print(f'校验 {fname} ...')
    real_md5 = md5(tmp)
    if real_md5 != EXPECTED_MD5[fname]:
        print(f'MD5 不匹配! 期望: {EXPECTED_MD5[fname]} 实际: {real_md5}')
        os.remove(tmp)
        sys.exit(1)
    print(f'校验通过 ({real_md5})')


def _move_to_model_dir(tmp: str, model_dir: str, fname: str) -> None:
    """将文件移动到模型目录"""
    dst = os.path.join(model_dir, fname)
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(tmp, dst)
    print(f'已移动到 {dst}')


def download_models(
    choice: str,
    mirror: dict[str, Any],
    model_dir: str,
) -> None:
    """下载所有模型文件"""
    print_step('4. 下载模型文件')
    for fname in MODEL_FILES:
        print(f'\n--- 处理: {fname} ---')
        tmp = os.path.join(os.getcwd(), fname)
        _download_one(fname, choice, mirror, tmp)
        _verify_md5(fname, tmp)
        _move_to_model_dir(tmp, model_dir, fname)


def verify_loading(model_dir: str) -> None:
    """验证 EasyOCR 模型加载"""
    print_step('5. 验证 EasyOCR 加载')
    try:
        import easyocr

        easyocr.Reader(
            ['ch_sim', 'en'],
            model_storage_directory=model_dir,
            download_enabled=False,
            verbose=False,
        )
        print('验证成功，模型可正常加载。')
    except Exception as e:
        print(f'验证失败: {e}')


def main() -> None:
    print_step('EasyOCR 模型下载助手')

    easyocr_ok = check_easyocr()
    model_dir = prepare_model_dir()
    choice, mirror = select_mirror()
    download_models(choice, mirror, model_dir)

    print_step('所有模型就绪')

    if easyocr_ok:
        verify_loading(model_dir)
    else:
        print_step('5. 跳过验证 (EasyOCR 未安装)')

    print('\n脚本完成。')


if __name__ == '__main__':
    main()
