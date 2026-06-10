"""掌纹 ROI 提取（Zhang et al. 2017 非接触 ROI 方案，MediaPipe 关键点版）。

参考：L. Zhang, et al. "Towards contactless palmprint recognition",
Pattern Recognition 69 (2017) 199-212. 第 4 节 / Table 2。

思路：用食指-中指缝、无名指-小指缝两个指缝关键点 X1/X2 自适应建立局部
坐标系（X 轴 = X1X2，原点 = 中点，Y 轴垂直指向掌心），再按 |X1X2| 定尺度
裁取掌心方形 ROI。该坐标系对平移、旋转、尺度变化鲁棒，是达到文献级 EER 的
关键前提。

关键点来源由 MediaPipe HandLandmarker 提供（见 algorithm/hand_landmarks.py），
替代了原先脆弱的 HSV 肤色分割 + 距离-角度谱指缝检测。检测不到手则返回 None，
由上层拒识。
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

import config
from algorithm.hand_landmarks import hand_keypoints

_ROI_SAMPLE = 176  # 仿射内部采样边长，preprocess 再统一缩放到 ROI_SIZE


@dataclass(frozen=True)
class RoiResult:
    """ROI 提取结果（带状态/原因/质量，供实时引导与多帧选优）。

    status: ok / no_hand / out_of_bounds
    quality: 仅 status==ok 时有意义，越大越清晰（拉普拉斯方差，纹路对比度代理）。
    hand_side: "L"（左手）/ "R"（右手）/ ""（未检测）。
    """

    status: str
    reason: str
    detail: str = ""  # 细分原因码（诊断用），如 mp_no_hand / warp_oob / ok
    roi: np.ndarray | None = None
    mask: np.ndarray | None = None
    quality: float = 0.0
    hand_side: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


_REASONS = {
    "no_hand": "请将手掌放入框内",
    "out_of_bounds": "请将手掌移到画面中央，保持适当距离",
    "ok": "手掌位置良好，可以开始",
}


# ── 检测诊断计数 ──────────────────────────────────────────────────────────────
# 每次 extract_palm_roi_ex 调用按 detail 码累加，供 /api/detect_stats 拉直方图，
# 用数据定位手掌检测不稳定的瓶颈在哪道门。Flask threaded=True，故加锁。
_STATS: Counter = Counter()
_STATS_LOCK = threading.Lock()


def _record(res: RoiResult) -> RoiResult:
    with _STATS_LOCK:
        _STATS[res.detail or res.status] += 1
    return res


def get_detect_stats() -> dict:
    with _STATS_LOCK:
        counts = dict(_STATS)
    total = sum(counts.values())
    ok = counts.get("ok", 0)
    return {
        "counts": counts,
        "total": total,
        "ok": ok,
        "ok_rate": round(ok / total, 4) if total else 0.0,
    }


def reset_detect_stats() -> None:
    with _STATS_LOCK:
        _STATS.clear()


def _roi_quality(patch: np.ndarray) -> tuple[float, float]:
    """返回归一化后的 (清晰度, 对比度)，均在 0~1 范围。

    清晰度 = 拉普拉斯方差 / 参考值（掌纹典型清晰图约 500~1000）。
    对比度 = 像素标准差 / 参考值（掌纹灰度图约 50~80）。
    """
    clarity = min(float(cv2.Laplacian(patch, cv2.CV_64F).var()) / 800.0, 1.0)
    contrast = min(float(np.std(patch)) / 70.0, 1.0)
    return clarity, contrast


def _warp_roi_from_keypoints(
    gray: np.ndarray,
    x1: np.ndarray,
    x2: np.ndarray,
    center: tuple[float, float],
    size: int = _ROI_SAMPLE,
) -> tuple[np.ndarray, np.ndarray] | None:
    """由 X1/X2 建立局部坐标系并仿射采样方形 ROI。"""
    c = np.array(center, dtype=np.float32)
    p1 = x1.astype(np.float32)
    p2 = x2.astype(np.float32)

    u = p2 - p1
    base = float(np.linalg.norm(u))
    if base < 1e-3:
        return None
    u = u / base

    n = np.array([-u[1], u[0]], dtype=np.float32)
    origin = (p1 + p2) / 2.0
    if np.dot(c - origin, n) < 0:  # Y 轴指向掌心
        n = -n

    side = config.ROI_PALM_SCALE * base       # 边长 ∝ 两指缝间距，实现尺度归一
    offset = config.ROI_PALM_OFFSET * base     # ROI 上沿离指缝线的距离（向掌心）
    top_mid = origin + offset * n
    top_left = top_mid - 0.5 * side * u

    h, w = gray.shape[:2]
    dst = np.array([[0, 0], [size - 1, 0], [0, size - 1]], dtype=np.float32)
    src = np.array(
        [top_left, top_left + side * u, top_left + side * n],
        dtype=np.float32,
    )
    # ROI 若大幅越界说明关键点不可靠，拒绝
    if np.any(src < -0.25 * size) or np.any(src[:, 0] > w + 0.25 * size) or np.any(src[:, 1] > h + 0.25 * size):
        return None

    mat = cv2.getAffineTransform(src, dst)
    patch = cv2.warpAffine(gray, mat, (size, size), flags=cv2.INTER_LINEAR)
    patch_mask = np.full((size, size), 255, dtype=np.uint8)
    return patch, patch_mask


def guide_box(w: int, h: int) -> tuple[int, int, int, int]:
    """由 config 比例算出引导框像素范围 (x0, y0, x1, y1)，并裁剪到画面内。"""
    side = config.ROI_GUIDE_SIDE * w
    cx, cy = config.ROI_GUIDE_CX * w, config.ROI_GUIDE_CY * h
    x0 = max(0, int(round(cx - side / 2)))
    y0 = max(0, int(round(cy - side / 2)))
    x1 = min(w, int(round(cx + side / 2)))
    y1 = min(h, int(round(cy + side / 2)))
    return x0, y0, x1, y1


def extract_palm_roi_ex(gray: np.ndarray, bgr: np.ndarray | None = None) -> RoiResult:
    """MediaPipe 关键点 → 局部坐标系裁 ROI，带诊断。

    返回 RoiResult，标明成功/失败原因，便于实时引导与多帧选优。
    检测只在引导框区域内进行，排除框外干扰。
    """
    H, W = gray.shape[:2]
    gx0, gy0, gx1, gy1 = guide_box(W, H)
    gray = gray[gy0:gy1, gx0:gx1]  # 之后所有处理都在引导框裁剪图上
    bgr_crop = bgr[gy0:gy1, gx0:gx1] if bgr is not None else None

    if bgr_crop is None:
        # MediaPipe 需要彩色图；无彩色帧无法检测
        return _record(RoiResult("no_hand", _REASONS["no_hand"], detail="no_color"))

    kp = hand_keypoints(bgr_crop)
    if kp is None:
        return _record(RoiResult("no_hand", _REASONS["no_hand"], detail="mp_no_hand"))
    x1, x2, center, _pts, hand_side = kp

    warped = _warp_roi_from_keypoints(gray, x1, x2, center)
    if warped is None:
        return _record(RoiResult("out_of_bounds", _REASONS["out_of_bounds"], detail="warp_oob"))

    patch, patch_mask = warped
    clarity, contrast = _roi_quality(patch)
    coverage = float((patch_mask > 0).mean()) if patch_mask is not None else 0.0
    quality = 0.5 * coverage + 0.3 * clarity + 0.2 * contrast
    return _record(RoiResult("ok", _REASONS["ok"], roi=patch, mask=patch_mask, quality=quality, detail="ok", hand_side=hand_side))


def extract_palm_roi(gray: np.ndarray, bgr: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    """MediaPipe 关键点 → 局部坐标系裁 ROI。失败返回 None。"""
    res = extract_palm_roi_ex(gray, bgr)
    if res.ok and res.roi is not None and res.mask is not None:
        return res.roi, res.mask
    return None


def debug_geometry(gray: np.ndarray, bgr: np.ndarray | None = None) -> dict:
    """返回供前端可视化的检测几何：21 个手部关键点 + 两个指缝点 X1/X2 + 状态。

    检测在引导框裁剪图上进行，坐标平移回整帧供叠加层绘制。状态判定与
    extract_palm_roi_ex 保持一致（能否裁出 ROI）。
    """
    H, W = gray.shape[:2]
    gx0, gy0, gx1, gy1 = guide_box(W, H)
    bgr_crop = bgr[gy0:gy1, gx0:gx1] if bgr is not None else None
    out: dict = {
        "status": "no_hand",
        "reason": _REASONS["no_hand"],
        "quality": 0.0,
        "landmarks": [],
        "x1": None,
        "x2": None,
        "guide_box": [gx0, gy0, gx1, gy1],
        "hand_side": "",
    }
    if bgr_crop is None:
        return out

    kp = hand_keypoints(bgr_crop)
    if kp is None:
        return out
    x1, x2, center, pts, hand_side = kp
    out["landmarks"] = [(float(p[0] + gx0), float(p[1] + gy0)) for p in pts]
    out["x1"] = (float(x1[0] + gx0), float(x1[1] + gy0))
    out["x2"] = (float(x2[0] + gx0), float(x2[1] + gy0))
    out["hand_side"] = hand_side

    gray_crop = gray[gy0:gy1, gx0:gx1]
    warped = _warp_roi_from_keypoints(gray_crop, x1, x2, center)
    if warped is None:
        out["status"] = "out_of_bounds"
        out["reason"] = _REASONS["out_of_bounds"]
    else:
        out["status"] = "ok"
        out["reason"] = _REASONS["ok"]
        clarity, contrast = _roi_quality(warped[0])
        coverage = float((warped[1] > 0).mean()) if warped[1] is not None else 0.0
        out["quality"] = round(0.5 * coverage + 0.3 * clarity + 0.2 * contrast, 2)
    return out


def center_square_crop(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    return gray[y0 : y0 + side, x0 : x0 + side]


def crop_roi_box(gray: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    h, w = gray.shape[:2]
    x, y, bw, bh = box
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    bw = max(1, min(bw, w - x))
    bh = max(1, min(bh, h - y))
    return gray[y : y + bh, x : x + bw]
