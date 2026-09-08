"""Crop one source screenshot into the standard 1x/2x/4x/8x layout."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from tools.ocr_crop_tool import CropToolError, _write_png


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PACKAGE_ROOT / 'result' / 'screenshot'
SCALES = (1, 2, 4, 8)


def _parse_roi(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(item) for item in value.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('ROI must be x1,y1,x2,y2') from exc
    if len(values) != 4 or not all(0.0 <= value <= 1.0 for value in values):
        raise argparse.ArgumentTypeError('ROI values must be in [0, 1]')
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise argparse.ArgumentTypeError('ROI upper-left must precede lower-right')
    return values


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('-i', '--image', type=Path, required=True)
    parser.add_argument('--roi', type=_parse_roi, required=True, metavar='X1,Y1,X2,Y2')
    parser.add_argument('-o', '--output-root', type=Path, default=RESULT_ROOT)


def run(args: argparse.Namespace) -> int:
    image = cv2.imread(str(args.image))
    if image is None:
        raise CropToolError(f'cannot read image: {args.image}')
    height, width = image.shape[:2]
    x1, y1, x2, y2 = args.roi
    left, top = int(x1 * width), int(y1 * height)
    right, bottom = int(x2 * width), int(y2 * height)
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        raise CropToolError('ROI produced an empty image')

    stem = args.image.stem
    target = args.output_root / stem
    _write_png(target / f'{stem}.png', image)
    for scale in SCALES:
        output = (
            crop
            if scale == 1
            else cv2.resize(
                crop,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
        )
        _write_png(target / f'{scale}x' / f'{stem}_roi_{scale}x.png', output)
    print(target)
    return 0
