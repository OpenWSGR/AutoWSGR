# Debug Toolkit

This folder is the Agent-facing debug package. Run it from the repository root
with `uv run python tools/debug_toolkit/main.py ...` or
`uv run python -m tools.debug_toolkit ...`.

```text
main.py
function/
  e2e.py
  e2e_runner/   full copy of the original tools/e2e package
  screenshot.py
  roi.py
  ocr.py
adb/
result/
```

## Commands

```text
python tools/debug_toolkit/main.py screenshot --serial 127.0.0.1:16384
python tools/debug_toolkit/main.py roi --image result/screenshot/screenshot_*.png --roi 0.25,0.33,0.47,0.60
python tools/debug_toolkit/main.py ocr --image result/screenshot/screenshot_*/1x/screenshot_*_roi_1x.png
python tools/debug_toolkit/main.py e2e --serial 127.0.0.1:16384 --with-ocr decisive --times 1
```

## Output

```text
result/
  logs/       copied E2E run logs
  screenshot/ timestamped screenshots and per-screenshot ROI folders
  ocr/        JSON OCR results
```

For an input named `screenshot_20260909_120000.png`, ROI output is:

```text
result/screenshot/screenshot_20260909_120000/
  screenshot_20260909_120000.png
  1x/screenshot_20260909_120000_roi_1x.png
  2x/screenshot_20260909_120000_roi_2x.png
  4x/screenshot_20260909_120000_roi_4x.png
  8x/screenshot_20260909_120000_roi_8x.png
```

The package includes `adb/adb.exe` and its Windows runtime DLLs. Existing
standalone tools and `tools/e2e` remain compatible.
