"""数据集发现与加载：支持 Kaggle 类「每人一个子目录」结构。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class Sample:
    path: Path
    label: str
    label_id: int
    session: str = ""  # 跨 session 协议用；普通数据集留空


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def _class_dirs(root: Path) -> list[Path]:
    """在 root 或其常见子目录下找类别文件夹。"""
    candidates: list[Path] = []
    if root.is_dir():
        subdirs = [p for p in root.iterdir() if p.is_dir()]
        if subdirs and any(any(_is_image(f) for f in p.iterdir() if f.is_file()) for p in subdirs):
            candidates = subdirs
        else:
            for name in ("train", "images", "data", "palm", "Palms"):
                nested = root / name
                if nested.is_dir():
                    inner = [p for p in nested.iterdir() if p.is_dir()]
                    if inner:
                        candidates = inner
                        break
    return sorted(candidates, key=lambda p: p.name.lower())


def discover_grouped_sessions(
    root: Path,
    *,
    images_per_identity: int = 10,
) -> list[Sample]:
    """Tongji 类扁平结构：session*/00001.tiff，按连续 N 张视为同一掌。

    Tongji 非接触掌纹库每掌 10 张（00001~00010 第 1 掌，依此类推），故
    ``images_per_identity=10``。
    """
    sessions = sorted(p for p in root.iterdir() if p.is_dir())
    if not sessions:
        sessions = [root]

    samples: list[Sample] = []
    label_id = 0
    for session in sessions:
        images = sorted(p for p in session.iterdir() if p.is_file() and _is_image(p))
        if not images:
            continue
        for start in range(0, len(images), images_per_identity):
            chunk = images[start : start + images_per_identity]
            if len(chunk) < 2:
                continue
            label = f"{session.name}_person_{label_id:05d}"
            for path in chunk:
                samples.append(Sample(path=path, label=label, label_id=label_id))
            label_id += 1
    if not samples:
        raise ValueError(f"no grouped session images under {root}")
    return samples


def discover_cross_session(
    root: Path | str,
    *,
    images_per_identity: int = 10,
) -> list[Sample]:
    """跨 session 发现：root/session1, root/session2，同名图为同一掌、不同期。

    palm_id = (序号-1) // images_per_identity，session1/session2 共享 palm_id 但
    session 字段不同。适用于 Tongji 官方 ROI（.bmp）与原图结构。
    """
    root = Path(root)
    sessions = sorted(p for p in root.iterdir() if p.is_dir() and p.name.lower().startswith("session"))
    if not sessions:
        raise ValueError(f"no session* folders under {root}")

    samples: list[Sample] = []
    for session in sessions:
        images = sorted(p for p in session.iterdir() if p.is_file() and _is_image(p))
        for order, path in enumerate(images):
            palm_id = order // images_per_identity
            samples.append(
                Sample(
                    path=path,
                    label=f"palm_{palm_id:04d}",
                    label_id=palm_id,
                    session=session.name,
                )
            )
    if not samples:
        raise ValueError(f"no images under {root}/session*")
    return samples


def _looks_like_grouped_sessions(root: Path) -> bool:
    sessions = [p for p in root.iterdir() if p.is_dir()]
    if not sessions:
        return False
    for session in sessions:
        files = [p for p in session.iterdir() if p.is_file() and _is_image(p)]
        if len(files) >= 10 and any(p.suffix.lower() in {".tif", ".tiff"} for p in files):
            return True
    return False


def discover_dataset(
    root: Path | str,
    *,
    images_per_identity: int = 10,
) -> list[Sample]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"dataset directory not found: {root}")

    if _looks_like_grouped_sessions(root):
        return discover_grouped_sessions(root, images_per_identity=images_per_identity)

    class_dirs = _class_dirs(root)
    if not class_dirs:
        images = sorted(p for p in root.rglob("*") if p.is_file() and _is_image(p))
        if not images:
            raise ValueError(f"no images found under {root}")
        labels = sorted({p.parent.name for p in images})
        label_to_id = {name: i for i, name in enumerate(labels)}
        return [
            Sample(path=p, label=p.parent.name, label_id=label_to_id[p.parent.name])
            for p in images
        ]

    samples: list[Sample] = []
    for i, class_dir in enumerate(class_dirs):
        for img in sorted(class_dir.iterdir()):
            if img.is_file() and _is_image(img):
                samples.append(Sample(path=img, label=class_dir.name, label_id=i))
    if not samples:
        raise ValueError(f"no images found under {root}")
    return samples


def load_image(path: Path | str) -> np.ndarray:
    path = Path(path)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"failed to read image: {path}")
    return img


def subsample(samples: list[Sample], *, max_persons: int | None, max_per_person: int | None) -> list[Sample]:
    if max_persons is None and max_per_person is None:
        return samples

    by_label: dict[str, list[Sample]] = {}
    for s in samples:
        by_label.setdefault(s.label, []).append(s)

    labels = sorted(by_label.keys())
    if max_persons is not None:
        labels = labels[:max_persons]

    out: list[Sample] = []
    for label in labels:
        group = by_label[label]
        if max_per_person is not None:
            group = group[:max_per_person]
        out.extend(group)
    return out
