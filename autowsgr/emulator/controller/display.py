"""Locate an application's display in ``dumpsys activity activities`` output."""

from __future__ import annotations

import re


_DISPLAY_HEADER = re.compile(r'^(?P<indent>\s*)Display #(?P<id>\d+)\b')
_RESUMED_ACTIVITY = re.compile(r'\b(?:mResumedActivity|topResumedActivity|Resumed)\b')
_LIVE_ACTIVITY = re.compile(r'^\s*\*\s+(?:Hist\s+#\d+:|ActivityRecord\b)')
_GLOBAL_SUMMARY = re.compile(
    r'^\s*(?:ResumedActivity|mFocusedActivity|mFocusedApp|mFocusedRootTask)\s*[:=]'
)


def find_package_display(activity_dump: str, package: str) -> int | None:
    """Return a package's display, preferring its resumed activity.

    Only inspect the indented contents of individual ``Display #N`` blocks.
    Android also prints global focus summaries after these blocks; attributing
    those summaries to the last display can silently select the launcher screen.
    Match a full package/component pair so channel packages cannot match a prefix.
    """
    if not package:
        return None
    component = re.compile(r'(?<![\w.])' + re.escape(package) + r'/[\w.$]+')
    current_display: int | None = None
    display_indent = 0
    candidates: list[int] = []
    for line in activity_dump.splitlines():
        header = _DISPLAY_HEADER.match(line)
        if header:
            current_display = int(header['id'])
            display_indent = len(header['indent'])
            continue
        if not line.strip() or current_display is None:
            continue
        # 部分 Android 的 Display 标题没有缩进，全局摘要却缩进 2 格。
        # 该独立摘要不是任何 Display 的子项，不能仅凭缩进判归属。
        if _GLOBAL_SUMMARY.match(line):
            current_display = None
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= display_indent:
            current_display = None
            continue
        if component.search(line):
            if _RESUMED_ACTIVITY.search(line):
                return current_display
            if _LIVE_ACTIVITY.match(line) and current_display not in candidates:
                candidates.append(current_display)
    return candidates[0] if candidates else None
