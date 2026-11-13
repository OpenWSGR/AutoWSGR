"""原始观察档案；流程标签与控制器预测分开保存。"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

import cv2

from autowsgr.emulator.frame import CapturedFrame


if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np


class FileStopEvent(threading.Event):
    """停止文件是显式停止入口，战斗识别循环仍使用现有 Event 接口。"""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def is_set(self) -> bool:
        if self.path.exists():
            self.set()
        return super().is_set()


class SampleArchive:
    """逐条落盘；进程中断时已保存的 PNG 与 JSONL 仍可使用。"""

    def __init__(self, output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise FileExistsError(f'采集目录必须为空，请为本次运行指定新目录: {output}')
        self.output = output
        self.images = output / 'images'
        self.images.mkdir(exist_ok=True)
        self.native_version = version('autowsgr_native')
        self.context: dict[str, Any] = {}
        self.counter = 0
        self.capture_phase: str | None = None

    def write_json(self, name: str, value: object) -> None:
        path = self.output / name
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)

    def record(
        self,
        kind: str,
        frame: CapturedFrame | None = None,
        *,
        crop: np.ndarray | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        self.counter += 1
        row = {
            **self.context,
            'sample_id': self.counter,
            'kind': kind,
            'recorded_at': datetime.now(UTC).isoformat(),
            'recorded_monotonic': time.monotonic(),
            'native_version': self.native_version,
            **fields,
        }
        for suffix, pixels in [('frame', frame.image if frame else None), ('crop', crop)]:
            if pixels is None:
                continue
            relative = f'images/{self.counter:06d}-{kind}-{suffix}.png'
            encoded, data = cv2.imencode('.png', cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
            if not encoded:
                raise OSError(f'无法编码采集图像: {relative}')
            (self.output / relative).write_bytes(data.tobytes())
            row[suffix] = relative
        if frame is not None:
            row.update(frame_sequence=frame.sequence, captured_at=frame.captured_at)
        with (self.output / 'observations.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
        self.write_json('progress.json', {'pid': os.getpid(), **row})
        return row


class RecordingDevice:
    """保留真实帧标识；仅通关流程临时保存每次读取到的页面。"""

    def __init__(self, device: Any, archive: SampleArchive, stop_event: FileStopEvent) -> None:
        self.device = device
        self.archive = archive
        self.stop_event = stop_event
        self._last_recorded: tuple[str, int | None] | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.device, name)

    def capture_frame(self) -> CapturedFrame:
        frame = self.device.capture_frame()
        if not isinstance(frame, CapturedFrame):
            frame = CapturedFrame(self.device.screenshot(), None, time.monotonic())
        kind = self.archive.capture_phase
        key = (kind, frame.sequence)
        if kind is not None and (frame.sequence is None or key != self._last_recorded):
            self.archive.record(kind, frame)
            self._last_recorded = key
        return frame

    def screenshot(self) -> np.ndarray:
        return self.capture_frame().image

    def click(self, *args: Any, **kwargs: Any) -> Any:
        if self.stop_event.is_set():
            raise InterruptedError('决战采集收到停止请求')
        return self.device.click(*args, **kwargs)


class TimedProxy:
    """只计时指定调用，不额外调用识别器。"""

    def __init__(self, target: Any, method: str, timings: dict[str, float], name: str) -> None:
        self.target = target
        self.method = method
        self.timings = timings
        self.name = name

    def __getattr__(self, name: str) -> Any:
        function = getattr(self.target, name)
        if name != self.method:
            return function

        def measured(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.timings[self.name] = time.perf_counter() - start

        return measured
