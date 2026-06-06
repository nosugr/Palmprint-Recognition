"""S1.2 CompCode 特征编码：多方向 Gabor 竞争编码 → PalmTemplate。"""

from __future__ import annotations

import math
from functools import lru_cache

import cv2
import numpy as np

import config
from algorithm.template import PalmTemplate, make_template


def orientation_angles(n: int | None = None) -> list[float]:
    count = n if n is not None else config.GABOR_ORIENTATIONS
    step = math.pi / count
    return [i * step for i in range(count)]


@lru_cache(maxsize=1)
def gabor_kernels() -> tuple[np.ndarray, ...]:
    # 参数来自 config；变更后需新进程或 cache_clear
    ksize = config.GABOR_KSIZE
    sigma = config.GABOR_SIGMA
    lambd = config.GABOR_LAMBDA
    gamma = config.GABOR_GAMMA
    kernels: list[np.ndarray] = []
    for theta in orientation_angles():
        k = cv2.getGaborKernel(
            (ksize, ksize), sigma, theta, lambd, gamma, 0, ktype=cv2.CV_32F
        )
        kernels.append(k)
    return tuple(kernels)


def gabor_responses(roi: np.ndarray) -> np.ndarray:
    """返回 shape (n_orientations, H, W) 的 float32 响应。"""
    img = roi.astype(np.float32)
    responses = [cv2.filter2D(img, cv2.CV_32F, k) for k in gabor_kernels()]
    return np.stack(responses, axis=0)


def competitive_code(responses: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """取各方向最小响应（最强负响应）的索引作为 CompCode。"""
    code_map = np.argmin(responses, axis=0).astype(np.uint8)
    # 无效区编码置 0，由 mask 在匹配时排除
    return code_map


def reliability_mask(responses: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """过滤竞争强度过弱的像素（平坦无纹路区，方向不可靠）。

    竞争强度 = 各方向响应的极差。低分位数以下的像素方向编码近乎随机，
    保留它们会同时拉近 genuine 与 impostor，反而损害区分度。
    """
    q = config.COMPCODE_RELIABILITY_Q
    if q <= 0:
        return valid_mask
    strength = responses.max(axis=0) - responses.min(axis=0)
    if not valid_mask.any():
        return valid_mask
    thr = float(np.quantile(strength[valid_mask], q))
    return valid_mask & (strength >= thr)


def encode(roi: np.ndarray, valid_mask: np.ndarray) -> PalmTemplate:
    if roi.ndim != 2:
        raise ValueError("roi must be grayscale 2D")
    responses = gabor_responses(roi)
    code_map = competitive_code(responses, valid_mask)
    mask = reliability_mask(responses, valid_mask)
    return make_template(code_map, mask, version=config.TEMPLATE_VERSION)


def encode_image(
    image: np.ndarray, *, pre_extracted: bool = False
) -> PalmTemplate | None:
    """整图 → 模板。pre_extracted=True 表示输入已是裁好的 ROI。

    自动 ROI 提取失败（strict）时返回 None。
    """
    from algorithm.preprocess import preprocess

    result = preprocess(image, strict=not pre_extracted, pre_extracted=pre_extracted)
    if result is None:
        return None
    roi, mask = result
    return encode(roi, mask)
