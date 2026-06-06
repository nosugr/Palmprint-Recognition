"""批量编码并缓存 PalmTemplate，避免重复跑 Gabor。"""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict
from pathlib import Path

from algorithm.dataset import Sample, load_image
from algorithm.encode import encode_image
from algorithm.template import PalmTemplate


def encode_samples(
    samples: list[Sample],
    *,
    verbose: bool = True,
    pre_extracted: bool = False,
) -> list[tuple[Sample, PalmTemplate]]:
    """编码样本列表。ROI 提取失败（自动模式）的样本被跳过。"""
    out: list[tuple[Sample, PalmTemplate]] = []
    total = len(samples)
    skipped = 0
    for i, sample in enumerate(samples, 1):
        if verbose and (i == 1 or i % 200 == 0 or i == total):
            print(f"  encode [{i}/{total}] {sample.label} / {sample.path.name}")
        img = load_image(sample.path)
        tmpl = encode_image(img, pre_extracted=pre_extracted)
        if tmpl is None:
            skipped += 1
            continue
        out.append((sample, tmpl))
    if verbose and skipped:
        print(f"  skipped {skipped}/{total} samples (ROI extraction failed)")
    return out


def cache_path(dataset_root: Path, tag: str = "default") -> Path:
    safe = dataset_root.name.replace("/", "_")
    return Path("data/cache") / f"{safe}_{tag}.pkl"


def save_cache(pairs: list[tuple[Sample, PalmTemplate]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [(asdict(s), t) for s, t in pairs]
    path.write_bytes(pickle.dumps(payload))


def load_cache(path: Path) -> list[tuple[Sample, PalmTemplate]] | None:
    if not path.exists():
        return None
    payload = pickle.loads(path.read_bytes())
    out: list[tuple[Sample, PalmTemplate]] = []
    for s_dict, tmpl in payload:
        sample = Sample(
            path=Path(s_dict["path"]),
            label=s_dict["label"],
            label_id=s_dict["label_id"],
            session=s_dict.get("session", ""),
        )
        out.append((sample, tmpl))
    return out


def write_manifest(path: Path, *, dataset: str, count: int, persons: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"dataset": dataset, "templates": count, "persons": persons}, indent=2),
        encoding="utf-8",
    )
