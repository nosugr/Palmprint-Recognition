"""S1.1 预处理：分割/对齐/掌纹 ROI → CLAHE → 128×128 + mask。"""

from __future__ import annotations

import cv2
import numpy as np

import config
from algorithm.roi import center_square_crop, crop_roi_box, extract_palm_roi


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError(f"unsupported image shape: {image.shape}")


def apply_clahe(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def apply_bilateral(gray: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)


def build_valid_mask(roi: np.ndarray, extra: np.ndarray | None = None) -> np.ndarray:
    low, high = config.ROI_INTENSITY_LOW, config.ROI_INTENSITY_HIGH
    valid = (roi >= low) & (roi <= high)
    if extra is not None:
        em = extra > 0 if extra.dtype != bool else extra
        if em.shape != valid.shape:
            em = cv2.resize(em.astype(np.uint8), (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
        valid &= em
    return valid


def _resize_square(gray: np.ndarray, mask: np.ndarray | None, size: int) -> tuple[np.ndarray, np.ndarray]:
    roi = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    if mask is not None:
        m = cv2.resize(mask.astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST) > 0
    else:
        m = np.ones(gray.shape, dtype=bool)
    return roi, m


def finalize_patch(
    patch: np.ndarray,
    patch_mask: np.ndarray | None = None,
    *,
    roi_size: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """已裁好的 ROI patch → 去噪 + CLAHE → size×size + 有效掩码。

    供多帧选优场景复用：先用 roi.extract_palm_roi_ex 选出最优 patch，再调本函数
    归一化，避免在 preprocess 里重复跑一次手掌分割/指缝定位。
    """
    size = roi_size if roi_size is not None else config.ROI_SIZE
    patch = apply_bilateral(patch)
    patch = apply_clahe(patch)
    roi, resized_mask = _resize_square(patch, patch_mask, size)
    mask = build_valid_mask(roi, resized_mask)
    return roi, mask


def preprocess(
    image: np.ndarray,
    *,
    roi_size: int | None = None,
    roi_box: tuple[int, int, int, int] | None = None,
    strict: bool = False,
    pre_extracted: bool = False,
) -> tuple[np.ndarray, np.ndarray] | None:
    """分割/定位掌纹 ROI → 去噪 + CLAHE → size×size + 有效掩码。

    返回 (roi_gray uint8 H×W, valid_mask bool H×W)。

    - ``pre_extracted=True``：输入本身已是裁好的掌纹 ROI（如官方 ROI 数据集），
      跳过手掌分割与指缝定位，直接归一化。
    - ``strict=True``：自动 ROI 提取失败（指缝不可见等）时返回 ``None``，由上层
      拒识（门禁场景应提示用户重新放手）。
    - 否则回退到中心裁剪，保证总有输出（用于固定 ROI 框或测试）。
    """
    size = roi_size if roi_size is not None else config.ROI_SIZE
    box = roi_box if roi_box is not None else config.ROI_BOX

    gray = to_gray(image)

    patch: np.ndarray
    patch_mask: np.ndarray | None = None

    if pre_extracted:
        patch = gray
    elif box is not None:
        patch = crop_roi_box(gray, box)
    else:
        extracted = extract_palm_roi(gray)
        if extracted is not None:
            patch, patch_mask = extracted
        elif strict:
            return None
        else:
            patch = center_square_crop(gray)

    return finalize_patch(patch, patch_mask, roi_size=size)
