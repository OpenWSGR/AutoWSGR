"""像素特征标注工具 — 用于 PixelSignature 开发。

提供 tkinter GUI，支持：
    1. 连接模拟器实时截图 / 加载本地 PNG 图片
    2. 在截图上点击标注特征点
    3. 自动读取点击处 RGB 颜色
    4. 编辑签名名称、匹配策略、容差
    5. 导出为 Python 代码 / YAML 片段，可直接粘贴到项目中

运行方式::

    python tools/pixel_marker.py                          # 仅加载图片模式
    python tools/pixel_marker.py --serial emulator-5554   # 连接模拟器
    python tools/pixel_marker.py --config user_settings.yaml  # 从配置文件加载
    python tools/pixel_marker.py --image screenshot.png   # 从文件加载

快捷键::

    左键点击  —  在截图上添加标注点
    右键点击  —  删除最近的标注点
    Ctrl+S    —  导出 YAML
    Ctrl+C    —  复制 Python 代码到剪贴板
    F5        —  重新截图（需已连接模拟器）
    Delete    —  删除选中的标注点
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import TYPE_CHECKING

import cv2


# 项目根目录
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

if TYPE_CHECKING:
    import numpy as np

    from autowsgr.emulator import ADBController


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MarkedPoint:
    """标注的单个像素点。"""

    # 相对坐标 (0.0–1.0)
    rx: float
    ry: float
    # 绝对像素坐标
    px: int
    py: int
    # RGB 颜色
    r: int
    g: int
    b: int
    # 容差
    tolerance: float = 30.0

    @property
    def color_hex(self) -> str:
        """返回 #RRGGBB 用于 GUI 显示。"""
        return f'#{self.r:02x}{self.g:02x}{self.b:02x}'

    @property
    def color_rgb(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    def to_pixel_rule_code(self) -> str:
        """生成 PixelRule.of(...) 代码。"""
        return (
            f'PixelRule.of({self.rx:.4f}, {self.ry:.4f}, '
            f'({self.r}, {self.g}, {self.b}), tolerance={self.tolerance})'
        )

    def to_yaml_dict(self) -> dict:
        return {
            'x': round(self.rx, 4),
            'y': round(self.ry, 4),
            'color': [self.r, self.g, self.b],
            'tolerance': self.tolerance,
        }


@dataclass
class SignatureConfig:
    """签名配置。"""

    name: str = 'unnamed_page'
    strategy: str = 'all'  # all / any / count
    threshold: int = 0
    points: list[MarkedPoint] = field(default_factory=list)

    def to_python_code(self) -> str:
        """生成可粘贴的 Python 代码。"""
        lines = [
            f'{self.name} = PixelSignature(',
            f'    name="{self.name}",',
            f'    strategy=MatchStrategy.{self.strategy.upper()},',
        ]
        if self.strategy == 'count':
            lines.append(f'    threshold={self.threshold},')
        lines.append('    rules=[')
        for pt in self.points:
            lines.append(f'        {pt.to_pixel_rule_code()},')
        lines.append('    ],')
        lines.append(')')
        return '\n'.join(lines)

    def to_yaml_str(self) -> str:
        """生成 YAML 片段。"""
        lines = [
            f'name: {self.name}',
            f'strategy: {self.strategy}',
        ]
        if self.strategy == 'count':
            lines.append(f'threshold: {self.threshold}')
        lines.append('rules:')
        for pt in self.points:
            d = pt.to_yaml_dict()
            lines.append(
                f'  - {{x: {d["x"]}, y: {d["y"]}, '
                f'color: [{d["color"][0]}, {d["color"][1]}, {d["color"][2]}], '
                f'tolerance: {d["tolerance"]}}}'
            )
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# GUI 应用
# ═══════════════════════════════════════════════════════════════════════════════


# 标注点在画布上的圆半径
MARKER_RADIUS = 6
# 缩放后预览最大尺寸
PREVIEW_MAX_W = 960
PREVIEW_MAX_H = 540


class PixelMarkerApp:
    """像素标注工具主窗口。"""

    def __init__(
        self,
        serial: str | None = None,
        image_path: str | None = None,
    ) -> None:
        self._serial = serial
        self._controller: ADBController | None = None
        self._connected = False

        # 原始截图 (RGB, full resolution)
        self._image: np.ndarray | None = None
        self._img_w = 0
        self._img_h = 0
        # 用于 tkinter 显示的缩放图 (PIL ImageTk.PhotoImage)
        self._tk_photo: object | None = None
        # 缩放比例 (display / original)
        self._scale = 1.0

        # 标注数据
        self._config = SignatureConfig()
        # 画布上标注圆的 id → MarkedPoint 索引
        self._marker_ids: list[int] = []

        # ── 构建窗口 ──
        self._root = tk.Tk()
        self._root.title('AutoWSGR — 像素特征标注工具')
        self._root.geometry('1280x720')
        self._root.minsize(900, 500)
        self._build_ui()
        self._bind_keys()

        # 启动时自动加载图片
        if image_path:
            self._load_image_file(image_path)

    # ── UI 构建 ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self._root

        # ── 顶部工具栏 ──
        toolbar = ttk.Frame(root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=4)

        ttk.Button(toolbar, text='📷 截图', command=self._on_screenshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='📂 打开图片', command=self._on_open_image).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text='🔄 重新截图 (F5)', command=self._on_screenshot).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text='💾 保存截图', command=self._on_save_screenshot).pack(
            side=tk.LEFT, padx=2
        )

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(toolbar, text='签名名称:').pack(side=tk.LEFT, padx=2)
        self._name_var = tk.StringVar(value=self._config.name)
        ttk.Entry(toolbar, textvariable=self._name_var, width=20).pack(side=tk.LEFT, padx=2)

        ttk.Label(toolbar, text='策略:').pack(side=tk.LEFT, padx=2)
        self._strategy_var = tk.StringVar(value='all')
        ttk.Combobox(
            toolbar,
            textvariable=self._strategy_var,
            values=['all', 'any', 'count'],
            state='readonly',
            width=6,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Label(toolbar, text='容差:').pack(side=tk.LEFT, padx=2)
        self._tolerance_var = tk.DoubleVar(value=30.0)
        ttk.Spinbox(toolbar, textvariable=self._tolerance_var, from_=1, to=200, width=5).pack(
            side=tk.LEFT, padx=2
        )

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Button(toolbar, text=' 清空标注', command=self._on_clear_points).pack(
            side=tk.LEFT, padx=2
        )

        # ── 主区域：画布 + 侧边栏 ──
        main_pane = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 画布
        canvas_frame = ttk.Frame(main_pane)
        self._canvas = tk.Canvas(canvas_frame, bg='#2b2b2b', cursor='crosshair')
        self._canvas.pack(fill=tk.BOTH, expand=True)
        main_pane.add(canvas_frame, weight=3)

        # 侧边栏
        sidebar = ttk.Frame(main_pane, width=350)
        main_pane.add(sidebar, weight=1)

        # 标注点列表
        list_frame = ttk.LabelFrame(sidebar, text='标注点列表')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        cols = ('#', 'rx', 'ry', 'R', 'G', 'B', '色块')
        self._tree = ttk.Treeview(list_frame, columns=cols, show='headings', height=12)
        for c in cols:
            self._tree.heading(c, text=c)
        self._tree.column('#', width=30, anchor='center')
        self._tree.column('rx', width=55, anchor='center')
        self._tree.column('ry', width=55, anchor='center')
        self._tree.column('R', width=35, anchor='center')
        self._tree.column('G', width=35, anchor='center')
        self._tree.column('B', width=35, anchor='center')
        self._tree.column('色块', width=50, anchor='center')
        self._tree.pack(fill=tk.BOTH, expand=True)

        ttk.Button(list_frame, text='删除选中 (Del)', command=self._on_delete_selected).pack(
            fill=tk.X, padx=4, pady=2
        )

        # 鼠标位置实时信息
        info_frame = ttk.LabelFrame(sidebar, text='鼠标位置')
        info_frame.pack(fill=tk.X, padx=2, pady=2)
        self._mouse_info_var = tk.StringVar(value='移动鼠标到截图上查看')
        ttk.Label(info_frame, textvariable=self._mouse_info_var, wraplength=310).pack(
            padx=4, pady=4
        )

        # 导出区域
        export_frame = ttk.LabelFrame(sidebar, text='导出')
        export_frame.pack(fill=tk.X, padx=2, pady=2)

        btn_row = ttk.Frame(export_frame)
        btn_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(btn_row, text='📋 Python 代码', command=self._on_export_python).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_row, text='📋 YAML', command=self._on_export_yaml).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text='💾 保存 YAML', command=self._on_save_yaml).pack(
            side=tk.LEFT, padx=2
        )

        self._export_text = scrolledtext.ScrolledText(export_frame, height=8, font=('Consolas', 9))
        self._export_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # 状态栏
        self._status_var = tk.StringVar(value='就绪')
        ttk.Label(root, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            side=tk.BOTTOM,
            fill=tk.X,
            padx=4,
            pady=2,
        )

    def _bind_keys(self) -> None:
        self._canvas.bind('<Button-1>', self._on_canvas_click)
        self._canvas.bind('<Button-3>', self._on_canvas_right_click)
        self._canvas.bind('<Motion>', self._on_canvas_motion)
        self._root.bind('<F5>', lambda _: self._on_screenshot())
        self._root.bind('<Delete>', lambda _: self._on_delete_selected())
        self._root.bind('<Control-s>', lambda _: self._on_save_yaml())
        self._root.bind('<Control-c>', self._on_ctrl_c)

    # ── 设备连接 ──────────────────────────────────────────────────────────

    def _ensure_connected(self) -> bool:
        """确保模拟器已连接。返回 True 表示连接就绪。

        连接流程：
        1. 若已连接，直接返回
        2. 若指定了 serial，直接连接
        3. 若未指定 serial 但 serial 为 None，则触发自动检测
        """
        if self._connected and self._controller is not None:
            return True

        serial = self._serial

        if not serial:
            # 自动检测可用模拟器
            try:
                from autowsgr.emulator import detect_emulators, prompt_user_select

                candidates = detect_emulators()
                if not candidates:
                    messagebox.showerror(
                        '未检测到模拟器',
                        '未找到任何在线的 Android 设备或模拟器。\n\n'
                        '请确保：\n'
                        '1. 模拟器已启动\n'
                        '2. ADB 服务可用\n'
                        '3. 模拟器已授权连接',
                    )
                    self._status_var.set('未检测到模拟器')
                    return False

                if len(candidates) == 1:
                    serial = candidates[0].serial
                else:
                    # 多个设备，让用户选择（会在当前 TTY 中交互）
                    try:
                        serial = prompt_user_select(candidates)
                    except Exception:
                        # 非 TTY 环境，提示用户指定 serial
                        serials = ', '.join(c.serial for c in candidates)
                        messagebox.showerror(
                            '无法自动选择',
                            f'检测到多个在线设备：{serials}\n\n请使用 --serial 参数指定目标设备。',
                        )
                        self._status_var.set('多个设备，需指定 serial')
                        return False
            except Exception as exc:
                messagebox.showerror('自动检测失败', str(exc))
                self._status_var.set('自动检测失败')
                return False

        try:
            from autowsgr.emulator import ADBController
            from autowsgr.infra import setup_logger

            # 只输出错误及以上等级（避免 airtest 噪音）
            setup_logger(level='ERROR')

            self._status_var.set(f'正在连接 {serial} ...')
            self._root.update()

            ctrl = ADBController(serial=serial, screenshot_timeout=15.0)
            info = ctrl.connect()
            self._controller = ctrl
            self._connected = True
            self._serial = serial  # 保存成功的 serial
            self._status_var.set(
                f'已连接: {info.serial} ({info.resolution[0]}x{info.resolution[1]})'
            )
            return True
        except Exception as exc:
            messagebox.showerror('连接失败', f'无法连接设备:\n{exc}')
            self._status_var.set('连接失败')
            self._controller = None
            self._connected = False
            return False

    # ── 截图 / 加载 ──────────────────────────────────────────────────────

    def _on_screenshot(self) -> None:
        if not self._ensure_connected():
            return
        try:
            self._status_var.set('正在截图 ...')
            self._root.update()
            assert self._controller is not None
            screen = self._controller.screenshot()
            self._set_image(screen)
            h, w = screen.shape[:2]
            self._status_var.set(f'截图完成: {w}x{h}')
        except Exception as exc:
            messagebox.showerror('截图失败', str(exc))
            self._status_var.set('截图失败')

    def _on_open_image(self) -> None:
        path = filedialog.askopenfilename(
            title='选择截图文件',
            filetypes=[('图片文件', '*.png *.jpg *.jpeg *.bmp'), ('所有文件', '*.*')],
        )
        if path:
            self._load_image_file(path)

    def _on_save_screenshot(self) -> None:
        """保存当前截图到 logs/pixel_marker 目录。"""
        if self._image is None:
            messagebox.showwarning('警告', '还没有加载任何截图')
            return

        # 创建 logs/pixel_marker 目录
        log_dir = _ROOT / 'logs' / 'pixel_marker'
        log_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名：pixel_marker_YYYYMMDD_HHMMSS.png
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'pixel_marker_{timestamp}.png'
        filepath = log_dir / filename

        # 保存图片 (RGB → BGR for cv2)
        bgr = cv2.cvtColor(self._image, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(filepath), bgr)
        self._status_var.set(f'已保存截图: {filepath.relative_to(_ROOT)}')
        messagebox.showinfo('成功', f'截图已保存到:\n{filepath}')

    def _load_image_file(self, path: str) -> None:
        bgr = cv2.imread(path)
        if bgr is None:
            messagebox.showerror('加载失败', f'无法读取图片: {path}')
            return
        img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self._set_image(img)
        self._status_var.set(f'已加载: {Path(path).name}  ({img.shape[1]}x{img.shape[0]})')

    def _set_image(self, rgb: np.ndarray) -> None:
        """设置当前截图（RGB ndarray）。"""
        self._image = rgb
        self._img_h, self._img_w = rgb.shape[:2]

        # 计算缩放使图片适配画布
        canvas_w = max(self._canvas.winfo_width(), PREVIEW_MAX_W)
        canvas_h = max(self._canvas.winfo_height(), PREVIEW_MAX_H)
        scale_w = canvas_w / self._img_w
        scale_h = canvas_h / self._img_h
        self._scale = min(scale_w, scale_h, 1.0)

        disp_w = int(self._img_w * self._scale)
        disp_h = int(self._img_h * self._scale)

        # resize → PhotoImage（图像已是 RGB）
        display = rgb.copy()
        if self._scale < 1.0:
            display = cv2.resize(display, (disp_w, disp_h), interpolation=cv2.INTER_AREA)

        from PIL import Image, ImageTk

        pil_img = Image.fromarray(display)
        self._tk_photo = ImageTk.PhotoImage(pil_img)

        self._canvas.delete('all')
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_photo, tags='bg')
        self._canvas.config(scrollregion=(0, 0, disp_w, disp_h))

        # 重绘已有标注
        self._redraw_markers()

    # ── 画布交互 ─────────────────────────────────────────────────────────

    def _canvas_to_image(self, cx: int, cy: int) -> tuple[int, int] | None:
        """画布坐标 → 原始图片像素坐标。超出范围返回 None。"""
        if self._image is None:
            return None
        px = int(cx / self._scale)
        py = int(cy / self._scale)
        if 0 <= px < self._img_w and 0 <= py < self._img_h:
            return (px, py)
        return None

    def _on_canvas_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """左键点击：添加标注点。"""
        pos = self._canvas_to_image(event.x, event.y)
        if pos is None or self._image is None:
            return

        px, py = pos
        r, g, b = (
            int(self._image[py, px, 0]),
            int(self._image[py, px, 1]),
            int(self._image[py, px, 2]),
        )
        rx = round(px / self._img_w, 4)
        ry = round(py / self._img_h, 4)
        tol = self._tolerance_var.get()

        pt = MarkedPoint(rx=rx, ry=ry, px=px, py=py, r=r, g=g, b=b, tolerance=tol)
        self._config.points.append(pt)

        self._draw_marker(pt)
        self._refresh_tree()
        self._status_var.set(
            f'添加点 #{len(self._config.points)}: ({rx:.4f}, {ry:.4f}) RGB=({r},{g},{b})'
        )

    def _on_canvas_right_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """右键点击：删除最近的标注点。"""
        if not self._config.points:
            return
        pos = self._canvas_to_image(event.x, event.y)
        if pos is None:
            return
        px, py = pos

        # 找距离最近的点
        best_idx = -1
        best_dist = float('inf')
        for i, pt in enumerate(self._config.points):
            d = ((pt.px - px) ** 2 + (pt.py - py) ** 2) ** 0.5
            if d < best_dist:
                best_dist = d
                best_idx = i

        if best_idx >= 0 and best_dist < 30:
            removed = self._config.points.pop(best_idx)
            self._redraw_markers()
            self._refresh_tree()
            self._status_var.set(
                f'删除点: ({removed.rx:.4f}, {removed.ry:.4f}) RGB=({removed.r},{removed.g},{removed.b})'
            )

    def _on_canvas_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """鼠标移动：显示当前位置颜色。"""
        pos = self._canvas_to_image(event.x, event.y)
        if pos is None or self._image is None:
            self._mouse_info_var.set('鼠标超出图片范围')
            return
        px, py = pos
        r, g, b = (
            int(self._image[py, px, 0]),
            int(self._image[py, px, 1]),
            int(self._image[py, px, 2]),
        )
        rx = px / self._img_w
        ry = py / self._img_h
        self._mouse_info_var.set(
            f'像素: ({px}, {py})    相对: ({rx:.4f}, {ry:.4f})\n'
            f'RGB: ({r}, {g}, {b})    #{r:02x}{g:02x}{b:02x}'
        )

    # ── 标注绘制 ─────────────────────────────────────────────────────────

    def _draw_marker(self, pt: MarkedPoint) -> None:
        """在画布上绘制一个标注点。"""
        cx = int(pt.px * self._scale)
        cy = int(pt.py * self._scale)
        r = MARKER_RADIUS

        # 外圈白色 + 内圈颜色
        self._canvas.create_oval(
            cx - r - 1,
            cy - r - 1,
            cx + r + 1,
            cy + r + 1,
            outline='white',
            width=2,
            tags='marker',
        )
        self._canvas.create_oval(
            cx - r + 1,
            cy - r + 1,
            cx + r - 1,
            cy + r - 1,
            fill=pt.color_hex,
            outline='',
            tags='marker',
        )
        # 序号
        idx = len(self._config.points)
        self._canvas.create_text(
            cx + r + 4,
            cy - r - 2,
            text=str(idx),
            fill='yellow',
            anchor=tk.NW,
            font=('Consolas', 9, 'bold'),
            tags='marker',
        )

    def _redraw_markers(self) -> None:
        """清除并重新绘制所有标注点。"""
        self._canvas.delete('marker')
        for pt in self._config.points:
            self._draw_marker(pt)

    # ── 列表 ─────────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        """刷新标注点列表。"""
        self._tree.delete(*self._tree.get_children())
        for i, pt in enumerate(self._config.points, 1):
            self._tree.insert(
                '',
                'end',
                iid=str(i),
                values=(i, f'{pt.rx:.4f}', f'{pt.ry:.4f}', pt.r, pt.g, pt.b, pt.color_hex),
            )

    def _on_delete_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        indices = sorted([int(s) - 1 for s in sel], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self._config.points):
                self._config.points.pop(idx)
        self._redraw_markers()
        self._refresh_tree()
        self._status_var.set(f'已删除 {len(indices)} 个标注点')

    def _on_clear_points(self) -> None:
        if self._config.points:
            if messagebox.askyesno('确认', f'确定清空全部 {len(self._config.points)} 个标注点？'):
                self._config.points.clear()
                self._redraw_markers()
                self._refresh_tree()
                self._status_var.set('已清空所有标注点')

    # ── 导出 ─────────────────────────────────────────────────────────────

    def _sync_config(self) -> None:
        """同步 UI 值到 config。"""
        self._config.name = self._name_var.get().strip() or 'unnamed_page'
        self._config.strategy = self._strategy_var.get()
        try:
            self._config.threshold = int(self._tolerance_var.get())
        except (ValueError, TypeError):
            pass

    def _on_export_python(self) -> None:
        self._sync_config()
        if not self._config.points:
            messagebox.showinfo('提示', '还没有标注任何点')
            return
        code = self._config.to_python_code()
        self._export_text.delete('1.0', tk.END)
        self._export_text.insert(tk.END, code)
        self._copy_to_clipboard(code)
        self._status_var.set('Python 代码已生成并复制到剪贴板')

    def _on_export_yaml(self) -> None:
        self._sync_config()
        if not self._config.points:
            messagebox.showinfo('提示', '还没有标注任何点')
            return
        yaml_str = self._config.to_yaml_str()
        self._export_text.delete('1.0', tk.END)
        self._export_text.insert(tk.END, yaml_str)
        self._copy_to_clipboard(yaml_str)
        self._status_var.set('YAML 片段已生成并复制到剪贴板')

    def _on_save_yaml(self) -> None:
        self._sync_config()
        if not self._config.points:
            messagebox.showinfo('提示', '还没有标注任何点')
            return
        path = filedialog.asksaveasfilename(
            title='保存 YAML',
            defaultextension='.yaml',
            filetypes=[('YAML files', '*.yaml *.yml'), ('All files', '*.*')],
            initialfile=f'{self._config.name}.yaml',
        )
        if path:
            Path(path).write_text(self._config.to_yaml_str(), encoding='utf-8')
            self._status_var.set(f'已保存: {path}')

    def _on_ctrl_c(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """Ctrl+C：如果导出框有内容就复制。"""
        content = self._export_text.get('1.0', tk.END).strip()
        if content:
            self._copy_to_clipboard(content)
            self._status_var.set('已复制到剪贴板')

    def _copy_to_clipboard(self, text: str) -> None:
        self._root.clipboard_clear()
        self._root.clipboard_append(text)

    # ── 启动 ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description='AutoWSGR 像素特征标注工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例::

    # 仅图片模式（不连接模拟器）
    python tools/pixel_marker.py

    # 指定 serial 连接到模拟器
    python tools/pixel_marker.py --serial emulator-5554

    # 从本地截图文件加载
    python tools/pixel_marker.py --image screenshot.png

    # 组合使用
    python tools/pixel_marker.py --serial 127.0.0.1:16384 --image screenshot.png

    # 自动检测单个模拟器（无需指定 serial）
    python tools/pixel_marker.py
        """,
    )
    parser.add_argument(
        '--serial',
        '-s',
        help='ADB serial 地址（如 emulator-5554、127.0.0.1:16384）。不指定则自动检测。',
    )
    parser.add_argument(
        '--image',
        '-i',
        help='从文件加载本地截图（PNG/JPG）',
    )
    args = parser.parse_args()

    app = PixelMarkerApp(
        serial=args.serial,
        image_path=args.image,
    )
    app.run()


if __name__ == '__main__':
    main()
