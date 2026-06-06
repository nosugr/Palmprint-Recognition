"""生成演示用多类掌纹风格图像（无 Kaggle 时跑通标定流程）。

每类一种固定纹理 + 小幅扰动，模拟「同人相近、异人较远」。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def person_texture(seed: int, size: int = 256) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    f1, f2, f3 = rng.integers(4, 14, size=3)
    ph1, ph2, ph3 = rng.uniform(0, 2 * np.pi, size=3)
    tex = (
        np.sin(x / f1 + ph1)
        + np.cos(y / f2 + ph2)
        + np.sin((x + y) / f3 + ph3)
    )
    tex = (tex - tex.min()) / (tex.max() - tex.min())
    return (tex * 180 + 40).astype(np.uint8)


def variant(base: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    noise = rng.normal(0, 6, base.shape)
    out = np.clip(base.astype(np.float64) + noise, 0, 255).astype(np.uint8)
    dy, dx = int(rng.integers(-4, 5)), int(rng.integers(-4, 5))
    return np.roll(np.roll(out, dy, axis=0), dx, axis=1)


def to_bgr(gray: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo palm-like dataset")
    parser.add_argument("--out", type=Path, default=Path("data/demo"))
    parser.add_argument("--persons", type=int, default=10)
    parser.add_argument("--images-per-person", type=int, default=8)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for pid in range(args.persons):
        label = f"person_{pid:03d}"
        class_dir = args.out / label
        class_dir.mkdir(parents=True, exist_ok=True)
        base = person_texture(seed=pid * 9973, size=args.size)
        rng = np.random.default_rng(pid + 42)
        for idx in range(args.images_per_person):
            img = variant(base, rng) if idx > 0 else base
            path = class_dir / f"img_{idx:03d}.jpg"
            cv2.imwrite(str(path), to_bgr(img))
        print(f"  {label}: {args.images_per_person} images")

    print(f"Done → {args.out} ({args.persons} classes)")


if __name__ == "__main__":
    main()
