"""从战舰少女 Wiki 爬取舰娘图鉴并更新 autowsgr/data/shipnames.yaml。

功能
----
1. 抓取 https://www.zjsnrwiki.com/wiki/%E8%88%B0%E5%A8%98%E5%9B%BE%E9%89%B4
2. 解析普通图鉴 (No.1~) 和改造图鉴 (No.1001~) 以及非图鉴船只 (No.8xxx)
3. 将旧文件备份为 shipnames.yaml.old，再写入新文件
4. 末尾追加 Other (战例) 固定条目

用法
----
    python tools/update_shipnames.py

可选参数
--------
    --dry-run      仅打印解析结果，不写文件
    --no-backup    覆盖时不创建 .old 备份
    --proxy URL    HTTP/HTTPS 代理 (例: http://127.0.0.1:7890)
    --timeout N    请求超时秒数 (默认 15)
    --cache FILE   将原始 HTML 缓存到指定文件 (方便调试)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# ── 项目根路径 ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# ── UTF-8 输出兼容 (Windows 终端) ────────────────────────────────────────────
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass

# ────────────────────────────────────────────────────────────────────────────

WIKI_URL = "https://www.zjsnrwiki.com/wiki/%E8%88%B0%E5%A8%98%E5%9B%BE%E9%89%B4"
YAML_PATH = _ROOT / "autowsgr" / "data" / "shipnames.yaml"

# 非图鉴船只（手动维护，Wiki 页面上这几条没有链接文本，需要特殊处理）
_EXTRA_SHIPS: dict[str, str] = {
    "8007": "提尔比茨",
    "8009": "萝德尼",
    "8111": "华盛顿",
    "8116": "戈本",
}

# 末尾固定附加：战例
_OTHER_SECTION = """\
Other: # 战例
  - 肌肉记忆
  - 长跑训练
  - 航空训练
  - 训练的结晶
  - 黑科技
  - 防空伞
  - 守护之盾
  - 抱头蹲防
  - 关键一击
  - 久远的加护
"""


# ── 解析 ─────────────────────────────────────────────────────────────────────

def _fetch_html(url: str, proxy: str | None, timeout: int) -> str:
    """下载页面 HTML。"""
    try:
        import requests
    except ImportError as exc:
        raise SystemExit(
            "缺少依赖: requests\n请运行: pip install requests"
        ) from exc

    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _parse_ships(html: str) -> list[tuple[str, str]]:
    """从 HTML 中提取 (编号, 舰名全称) 列表，保持页面出现顺序。

    Wiki 页面中每条舰娘的标准结构（示例）::

        <td width="162px"><center><b>No.1</b></center></td>
        <td ... ><center><b><a href="...">胡德</a></b></center></td>

    同时兼容旧版本正则（方案 A），以及用 BeautifulSoup 解析（方案 B）。
    优先使用 BeautifulSoup，回退到正则。
    """
    # ── 方案 A：纯正则 ───────────────────────────────────────────────────────
    # 匹配形如  No.1  No.1001  No.8007  (允许空格)
    re_no = re.compile(
        r'<td[^>]*>\s*<center>\s*<b>\s*(No\.\s*\d+)\s*</b>\s*</center>\s*</td>',
        re.DOTALL,
    )
    re_name = re.compile(
        r'<td[^>]*>\s*<center>\s*<b>\s*<a\s[^>]*>(.*?)</a>\s*</b>\s*</center>\s*</td>',
        re.DOTALL,
    )

    nos   = [m.group(1).replace(" ", "").replace("No.", "") for m in re_no.finditer(html)]
    names = [m.group(1).strip() for m in re_name.finditer(html)]

    if nos and names:
        pairs = list(zip(nos, names, strict=False))
        print(f"  [正则] 解析到 {len(pairs)} 条舰娘")
        return pairs

    # ── 方案 B：BeautifulSoup ────────────────────────────────────────────────
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise SystemExit(
            "正则未能匹配，且缺少 bs4。\n"
            "请运行: pip install requests beautifulsoup4\n"
            "或启用代理后重新尝试。"
        )

    soup = BeautifulSoup(html, "html.parser")
    pairs: list[tuple[str, str]] = []

    # 查找所有包含 "No." 编号的 <td> 单元格
    for td in soup.find_all("td"):
        b_tag = td.find("b")
        if not b_tag:
            continue
        text = b_tag.get_text(strip=True)
        m = re.fullmatch(r"No\.(\d+)", text)
        if not m:
            continue
        no = m.group(1)

        # 找同行下一个含链接的 <td>
        sibling = td.find_next_sibling("td")
        while sibling:
            a_tag = sibling.find("a")
            if a_tag:
                pairs.append((no, a_tag.get_text(strip=True)))
                break
            sibling = sibling.find_next_sibling("td")

    print(f"  [BeautifulSoup] 解析到 {len(pairs)} 条舰娘")
    return pairs


def _ships_to_yaml(ships: list[tuple[str, str]], extra: dict[str, str]) -> str:
    """将 (编号, 全称) 列表转换为 YAML 文本。

    YAML 格式示例::

        No.1: # 胡德
          - "胡德"
        No.100: # 狮(战列舰)
          - "狮"
    """
    seen: set[str] = set()
    lines: list[str] = []

    def _add(no: str, full_name: str) -> None:
        key = f"No.{no}"
        if key in seen:
            return
        seen.add(key)
        # 短名：去掉括号内的补充说明
        short = re.sub(r"[\(（][^\)）]*[\)）]", "", full_name).strip()
        lines.append(f"{key}: # {full_name}")
        lines.append(f'  - "{short}"')

    for no, name in ships:
        _add(no, name)

    # 追加非图鉴船只（手动维护）
    for no, name in extra.items():
        _add(no, name)

    return "\n".join(lines) + "\n"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="爬取 Wiki 舰娘图鉴并更新 shipnames.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true", help="仅打印，不写文件")
    p.add_argument("--no-backup", action="store_true", help="不创建 .old 备份")
    p.add_argument("--proxy", default=None, metavar="URL", help="HTTP/HTTPS 代理地址")
    p.add_argument("--timeout", type=int, default=15, metavar="N", help="请求超时秒数")
    p.add_argument("--cache", default=None, metavar="FILE", help="将 HTML 缓存到文件")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("  舰娘图鉴 shipnames.yaml 更新工具")
    print("=" * 60)
    print(f"  来源: {WIKI_URL}")
    print(f"  目标: {YAML_PATH}")
    print(f"  代理: {args.proxy or '无'}")
    print()

    # ── 1. 获取 HTML ─────────────────────────────────────────────────────────
    print("  [1/4] 正在下载页面...")
    html = _fetch_html(WIKI_URL, proxy=args.proxy, timeout=args.timeout)
    print(f"  [OK] 下载完成，共 {len(html):,} 字节")

    if args.cache:
        cache_path = Path(args.cache)
        cache_path.write_text(html, encoding="utf-8")
        print(f"  [缓存] 已保存到: {cache_path}")

    # ── 2. 解析舰娘列表 ──────────────────────────────────────────────────────
    print()
    print("  [2/4] 正在解析舰娘数据...")
    ships = _parse_ships(html)

    if not ships:
        print("  [ERROR] 未解析到任何舰娘，请检查页面结构或使用 --cache 保存 HTML 调试")
        sys.exit(1)

    print(f"  [OK] 共解析 {len(ships)} 条（含普通图鉴 + 改造图鉴）")
    print(f"  [INFO] 另附加 {len(_EXTRA_SHIPS)} 条非图鉴船只（手动维护）")

    # ── 3. 生成 YAML 文本 ─────────────────────────────────────────────────────
    print()
    print("  [3/4] 正在生成 YAML...")
    yaml_body = _ships_to_yaml(ships, _EXTRA_SHIPS)
    yaml_text = yaml_body + _OTHER_SECTION

    total_lines = yaml_text.count("\n")
    print(f"  [OK] 生成 {total_lines} 行")

    # ── 预览前 10 行 ──────────────────────────────────────────────────────────
    print()
    print("  预览 (前 10 行):")
    for line in yaml_text.splitlines()[:10]:
        print(f"    {line}")
    print("    ...")
    print()

    if args.dry_run:
        print("  [DRY-RUN] 未写入文件（--dry-run 模式）")
        return

    # ── 4. 写入文件 ───────────────────────────────────────────────────────────
    print("  [4/4] 正在写入文件...")

    if YAML_PATH.exists() and not args.no_backup:
        backup_path = YAML_PATH.with_suffix(".yaml.old")
        shutil.copy2(YAML_PATH, backup_path)
        print(f"  [备份] 旧文件已备份到: {backup_path}")

    YAML_PATH.parent.mkdir(parents=True, exist_ok=True)
    YAML_PATH.write_text(yaml_text, encoding="utf-8")
    print(f"  [OK] 已写入: {YAML_PATH}")

    print()
    print("=" * 60)
    print("  更新完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
