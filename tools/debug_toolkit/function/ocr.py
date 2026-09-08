"""Run project OCR and write structured results under result/ocr."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import cv2

from autowsgr.vision import EasyOCREngine


if TYPE_CHECKING:
    import argparse


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PACKAGE_ROOT / 'result' / 'ocr'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('-i', '--image', type=Path, required=True)
    parser.add_argument('--allowlist', default='')
    parser.add_argument('-o', '--output-root', type=Path, default=RESULT_ROOT)


def run(args: argparse.Namespace) -> int:
    image = cv2.imread(str(args.image))
    if image is None:
        raise FileNotFoundError(args.image)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    engine = EasyOCREngine.create(gpu=False, mirror='modelscope')
    results = engine.recognize(rgb, allowlist=args.allowlist or None)
    payload = [
        {
            'text': result.text,
            'confidence': result.confidence,
            'bbox': result.bbox,
        }
        for result in results
    ]
    output = args.output_root / f'{args.image.stem}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    for result in payload:
        print(f'{result["text"]} ({result["confidence"]:.3f})')
    return 0
