"""S1.3 匹配：CompCode 环形方向距离 + shift matching。"""

from __future__ import annotations

import math

import numpy as np

import config
from algorithm.template import PalmTemplate, code_array, mask_array


def match_confidence(distance: float, threshold: float, *, sharpness: float = 18.0) -> float:
    """把匹配距离映射成 [0,1] 置信度（以阈值为决策边界的 sigmoid）。

    距离 == 阈值 → 0.5；明显小于阈值（典型同掌）→ 接近 1；大于阈值（异掌）→ 接近 0。
    sharpness 越大过渡越陡。仅用于展示，不参与判定（判定仍以 distance < threshold）。
    """
    try:
        return 1.0 / (1.0 + math.exp(sharpness * (distance - threshold)))
    except OverflowError:
        return 0.0 if distance > threshold else 1.0


def _check_compatible(a: PalmTemplate, b: PalmTemplate) -> None:
    if a.version != b.version:
        raise ValueError(f"version mismatch: {a.version} vs {b.version}")
    if (a.height, a.width) != (b.height, b.width):
        raise ValueError("shape mismatch")
    if a.bits_per_pixel != b.bits_per_pixel:
        raise ValueError("bits_per_pixel mismatch")


def circular_direction_distance(a: np.ndarray, b: np.ndarray, n_dirs: int) -> np.ndarray:
    """逐像素环形方向差，归一化到 [0, 1]。"""
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    circ = np.minimum(diff, n_dirs - diff)
    max_dist = n_dirs // 2
    return circ.astype(np.float64) / max_dist


def _shift_array(arr: np.ndarray, dy: int, dx: int) -> np.ndarray:
    h, w = arr.shape
    out = np.zeros_like(arr)
    src_y0 = max(0, -dy)
    src_y1 = min(h, h - dy)
    src_x0 = max(0, -dx)
    src_x1 = min(w, w - dx)
    dst_y0 = max(0, dy)
    dst_x0 = max(0, dx)
    dst_y1 = dst_y0 + (src_y1 - src_y0)
    dst_x1 = dst_x0 + (src_x1 - src_x0)
    if src_y1 <= src_y0 or src_x1 <= src_x0:
        return out
    out[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
    return out


def masked_mean_distance(
    code_a: np.ndarray,
    code_b: np.ndarray,
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    n_dirs: int,
) -> float:
    overlap = mask_a & mask_b
    count = int(overlap.sum())
    # 重叠区过小则不可信，判为最大距离
    if count < config.MATCH_MIN_OVERLAP_FRAC * code_a.size:
        return 1.0
    dist_map = circular_direction_distance(code_a, code_b, n_dirs)
    return float(np.mean(dist_map[overlap]))


def match_distance_arrays(
    code_a: np.ndarray,
    mask_a: np.ndarray,
    code_b: np.ndarray,
    mask_b: np.ndarray,
    *,
    max_shift: int | None = None,
    n_dirs: int | None = None,
) -> float:
    """数组级匹配（已解包的 code/mask）。批量评测时预解包一次、反复调用，避免
    每次 match_distance 重复 unpackbits 的固定开销。"""
    shift = max_shift if max_shift is not None else config.MATCH_MAX_SHIFT
    nd = n_dirs if n_dirs is not None else config.GABOR_ORIENTATIONS
    best = 1.0
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            shifted_b = _shift_array(code_b, dy, dx)
            shifted_mask_b = _shift_array(mask_b.astype(np.uint8), dy, dx).astype(bool)
            d = masked_mean_distance(code_a, shifted_b, mask_a, shifted_mask_b, nd)
            best = min(best, d)
    return best


def match_distance(
    a: PalmTemplate,
    b: PalmTemplate,
    max_shift: int | None = None,
) -> float:
    _check_compatible(a, b)
    return match_distance_arrays(
        code_array(a), mask_array(a), code_array(b), mask_array(b),
        max_shift=max_shift, n_dirs=config.GABOR_ORIENTATIONS,
    )


def match_best(
    probe: PalmTemplate,
    gallery: list[tuple[int, PalmTemplate]],
    threshold: float | None = None,
) -> tuple[bool, int | None, float]:
    """gallery: [(user_id, template), ...]。返回 (matched, user_id, min_distance)。"""
    thr = threshold if threshold is not None else config.get_match_threshold()
    best_uid: int | None = None
    best_dist = 1.0
    for uid, tmpl in gallery:
        d = match_distance(probe, tmpl)
        if d < best_dist:
            best_dist = d
            best_uid = uid
    matched = best_dist < thr
    return matched, best_uid if matched else None, best_dist
