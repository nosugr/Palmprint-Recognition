"""手掌分割与掌纹 ROI 提取（Zhang et al. 2017 非接触 ROI 方案）。

参考：L. Zhang, et al. "Towards contactless palmprint recognition",
Pattern Recognition 69 (2017) 199-212. 第 4 节 / Table 2。

思路：用食指-中指缝、无名指-小指缝两个指缝关键点 X1/X2 自适应建立局部
坐标系（X 轴 = X1X2，原点 = 中点，Y 轴垂直指向掌心），再按 |X1X2| 定尺度
裁取掌心方形 ROI。该坐标系对平移、旋转、尺度变化鲁棒，是达到文献级 EER 的
关键前提。指缝检测失败（手指未张开等）则返回 None，由上层拒识。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

import config

_ROI_SAMPLE = 176  # 谷点法内部采样边长，preprocess 再统一缩放到 ROI_SIZE


@dataclass(frozen=True)
class RoiResult:
    """ROI 提取结果（带状态/原因/质量，供实时引导与多帧选优）。

    status: ok / no_hand / bad_pose / out_of_bounds
    quality: 仅 status==ok 时有意义，越大越清晰（拉普拉斯方差，纹路对比度代理）。
    """

    status: str
    reason: str
    roi: np.ndarray | None = None
    mask: np.ndarray | None = None
    quality: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


_REASONS = {
    "no_hand": "请将手掌放入框内",
    "bad_pose": "请将五指张开的手掌正对摄像头",
    "out_of_bounds": "请将手掌移到画面中央，保持适当距离",
    "ok": "手掌位置良好，可以开始",
}


def _roi_quality(patch: np.ndarray) -> float:
    """纹路清晰度评分：拉普拉斯方差（对焦/对比度代理），越大越好。"""
    return float(cv2.Laplacian(patch, cv2.CV_64F).var())


def _solidity(contour: np.ndarray) -> float:
    """轮廓实心度 = 轮廓面积 / 凸包面积。张开五指因指缝凹陷而偏低（≈0.6–0.75），
    圆/拳头/脸等凸物体接近 1.0，用于排除占满画面的非张开手掌。"""
    area = cv2.contourArea(contour)
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    if hull_area < 1e-6:
        return 1.0
    return float(area / hull_area)


def _largest_contour(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _skin_mask(img: np.ndarray) -> np.ndarray:
    """HSV 肤色检测 → 二值掩码。输入灰度或 BGR 图。

    范围说明（覆盖黄/白/棕/黑种人 + 反光/阴影区域）：
    - H: 0-60  覆盖红→黄→橙色相（肤色主区间）
    - S: 15-255 低饱和度覆盖反光/高光区域（掌心反光时 S 很低）
    - V: 35-255 低亮度覆盖阴影区域（手指缝隙/手腕阴影）
    """
    if img.ndim == 2:
        return np.ones_like(img, dtype=np.uint8) * 255
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 15, 35], dtype=np.uint8)
    upper = np.array([60, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    return mask


def segment_hand_mask(gray: np.ndarray, bgr: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """分割手掌区域。暗背景场景：手掌比背景亮。"""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if binary.mean() > 127:  # 前景被判反则取反，保证手掌为白
        binary = cv2.bitwise_not(binary)

    skin = _skin_mask(bgr if bgr is not None else gray)
    binary = cv2.bitwise_and(binary, skin)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contour = _largest_contour(binary)
    if contour is None or cv2.contourArea(contour) < gray.size * 0.02:
        return np.zeros_like(gray, dtype=np.uint8), None

    mask = np.zeros_like(gray, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    return mask, contour


def palm_center(mask: np.ndarray) -> tuple[tuple[float, float], float]:
    """距离变换求最大内切圆：返回 (掌心(x,y), 内切半径 r)。

    手掌常触及图像边缘，先补一圈零边框强制边缘视为背景，避免内切圆被
    贴边的指/腕带偏。
    """
    padded = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    dist = cv2.distanceTransform(padded, cv2.DIST_L2, 5)
    _, max_val, _, max_loc = cv2.minMaxLoc(dist)
    return (float(max_loc[0] - 1), float(max_loc[1] - 1)), float(max_val)


def _smooth_circular(sig: np.ndarray, win: int) -> np.ndarray:
    if win < 3:
        return sig
    k = np.ones(win, dtype=np.float64) / win
    pad = win
    ext = np.concatenate([sig[-pad:], sig, sig[:pad]])
    sm = np.convolve(ext, k, mode="same")
    return sm[pad:-pad]


def _local_extrema(sig: np.ndarray, order: int) -> tuple[list[int], list[int]]:
    """返回 (极大值下标, 极小值下标)。order：邻域半径。"""
    n = len(sig)
    maxima: list[int] = []
    minima: list[int] = []
    for i in range(n):
        win = sig[max(0, i - order) : min(n, i + order + 1)]
        if sig[i] == win.max() and sig[i] > win.min():
            if not maxima or i - maxima[-1] > order:
                maxima.append(i)
        if sig[i] == win.min() and sig[i] < win.max():
            if not minima or i - minima[-1] > order:
                minima.append(i)
    return maxima, minima


def _finger_keypoints(
    contour: np.ndarray,
    center: tuple[float, float],
    radius: float,
    debug: dict | None = None,
) -> tuple[np.ndarray, np.ndarray] | None:
    """检测食指-中指缝、无名指-小指缝两个关键点 X1, X2（图像坐标）。

    手掌上半部分（指侧）按角度排成「距离-角度」谱：5 个指尖为极大、4 个
    指缝为极小。用相邻指尖最大角距判定拇指侧并剔除拇指，剩 4 指 3 谷，取
    外侧两谷即两个目标指缝。失败返回 None。
    """
    pts = contour.reshape(-1, 2).astype(np.float64)
    c = np.array(center, dtype=np.float64)
    rel = pts - c
    dist = np.hypot(rel[:, 0], rel[:, 1])

    # 取指侧（掌心上方）的点；图像 y 向下，故 y < cy 为上方
    finger_side = rel[:, 1] < -0.05 * radius
    if finger_side.sum() < 30:
        return None

    fp = pts[finger_side]
    frel = rel[finger_side]
    fdist = dist[finger_side]
    ang = np.arctan2(frel[:, 1], frel[:, 0])  # 上半区角度约在 (-π, 0)

    order_idx = np.argsort(ang)
    ang_s = ang[order_idx]
    dist_s = fdist[order_idx]
    pts_s = fp[order_idx]

    dist_sm = _smooth_circular(dist_s, max(5, len(dist_s) // 20))
    win = max(3, len(dist_s) // 18)
    maxima, _ = _local_extrema(dist_sm, win)

    # 仅保留显著指尖（距离 > 半径）且不在腕侧（|angle|≈180°）的峰
    maxima = [
        i for i in maxima
        if dist_sm[i] > 1.0 * radius and abs(ang_s[i]) < np.radians(170)
    ]
    if len(maxima) < config.ROI_FINGER_MIN_TIPS:
        return None

    # 合并同一指尖的「双峰」：角度相近者并为一个（保留更远的）
    maxima.sort(key=lambda i: ang_s[i])
    merged: list[int] = []
    min_sep = config.ROI_FINGER_MERGE_SEP  # rad，原硬编码 0.22，放宽以容忍光照不均
    for i in maxima:
        if merged and ang_s[i] - ang_s[merged[-1]] < min_sep:
            if dist_sm[i] > dist_sm[merged[-1]]:
                merged[-1] = i
            continue
        merged.append(i)
    if len(merged) < config.ROI_FINGER_MIN_TIPS:
        return None

    # 取最显著的 5 个手指再按角度排
    maxima = sorted(merged, key=lambda i: dist_sm[i], reverse=True)[:5]
    maxima = sorted(maxima, key=lambda i: ang_s[i])
    tip_ang = ang_s[maxima]

    # 5 指：用相邻指尖角距最大者（拇指-食指缝）判定并剔除拇指
    if len(maxima) >= 5:
        gaps_ang = np.diff(tip_ang)
        thumb_side = int(np.argmax(gaps_ang))
        if thumb_side <= len(gaps_ang) // 2:
            fingers = maxima[1:]   # 拇指在左端
        else:
            fingers = maxima[:-1]  # 拇指在右端
    else:
        fingers = maxima  # 仅 4 指（拇指未张开/未检出），视为食/中/无名/小
    if len(fingers) < config.ROI_FINGER_MIN_TIPS:
        return None
    fingers = fingers[:max(4, config.ROI_FINGER_MIN_TIPS)]
    if debug is not None:
        debug["fingertips"] = [pts_s[i] for i in fingers]

    # 在相邻手指之间各找一个谷点（极小），并校验指缝足够深
    valleys: list[np.ndarray] = []
    for a, b in zip(fingers[:-1], fingers[1:]):
        lo, hi = min(a, b), max(a, b)
        seg = dist_sm[lo : hi + 1]
        if len(seg) == 0:
            return None
        vidx = lo + int(np.argmin(seg))
        if debug is not None:
            debug.setdefault("valleys", []).append(pts_s[vidx])
        # 指缝深度门：谷点距离须明显小于相邻指尖，否则是圆/拳头边缘的"假指缝"
        tip_val = min(dist_sm[a], dist_sm[b])
        if tip_val <= 1e-6 or dist_sm[vidx] >= config.ROI_MAX_VALLEY_RATIO * tip_val:
            return None
        valleys.append(pts_s[vidx])
    # 4 指 3 谷：外侧两谷 = 食中缝 & 无名小缝
    # 3 指 2 谷：食中缝 & 中无名缝
    if len(valleys) >= 2:
        x1 = valleys[0]
        x2 = valleys[-1]
        return x1, x2
    return None


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
    """Zhang 方案，带诊断：分割 → 掌心 → 指缝关键点 → 局部坐标系裁 ROI。

    返回 RoiResult，标明成功/失败原因，便于实时引导与多帧选优。
    检测只在引导框区域内进行，排除框外人脸等干扰。
    """
    H, W = gray.shape[:2]
    gx0, gy0, gx1, gy1 = guide_box(W, H)
    gray = gray[gy0:gy1, gx0:gx1]  # 之后所有处理都在引导框裁剪图上
    bgr_crop = bgr[gy0:gy1, gx0:gx1] if bgr is not None else None

    hand_mask, contour = segment_hand_mask(gray, bgr_crop)
    if contour is None:
        return RoiResult("no_hand", _REASONS["no_hand"])

    h, w = gray.shape[:2]
    center, radius = palm_center(hand_mask)
    # 质量门：内切圆过小或圆心贴边 → 没有有效手掌
    if radius < 0.12 * min(h, w):
        return RoiResult("no_hand", _REASONS["no_hand"])
    if not (0.10 * w < center[0] < 0.90 * w and 0.10 * h < center[1] < 0.97 * h):
        return RoiResult("out_of_bounds", _REASONS["out_of_bounds"])

    # 实心度门：圆/拳头/脸等占满画面的凸物体 solidity≈1，张开五指因指缝凹陷而偏低。
    # 过高直接判为"未张开五指/非手掌"，挡住"东西占满框就显示位置良好"的误判。
    if _solidity(contour) > config.ROI_MAX_SOLIDITY:
        return RoiResult("bad_pose", _REASONS["bad_pose"])

    kp = _finger_keypoints(contour, center, radius)
    if kp is None:
        return RoiResult("bad_pose", _REASONS["bad_pose"])

    warped = _warp_roi_from_keypoints(gray, kp[0], kp[1], center)
    if warped is None:
        return RoiResult("out_of_bounds", _REASONS["out_of_bounds"])

    patch, patch_mask = warped
    return RoiResult("ok", _REASONS["ok"], roi=patch, mask=patch_mask, quality=_roi_quality(patch))


def extract_palm_roi(gray: np.ndarray, bgr: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    """Zhang 方案：分割 → 掌心 → 指缝关键点 → 局部坐标系裁 ROI。失败返回 None。"""
    res = extract_palm_roi_ex(gray, bgr)
    if res.ok and res.roi is not None and res.mask is not None:
        return res.roi, res.mask
    return None


def debug_geometry(gray: np.ndarray, bgr: np.ndarray | None = None) -> dict:
    """返回供前端可视化的检测几何：轮廓、掌心+内切圆、指尖、指缝、solidity 与状态。

    用于调试叠加层与 preview_status 的 solidity 读出，便于看清"后端把什么当成手"。
    检测在引导框裁剪图上进行，坐标平移回整帧供叠加层绘制。
    """
    H, W = gray.shape[:2]
    gx0, gy0, gx1, gy1 = guide_box(W, H)
    crop = gray[gy0:gy1, gx0:gx1]
    bgr_crop = bgr[gy0:gy1, gx0:gx1] if bgr is not None else None

    res = extract_palm_roi_ex(gray, bgr)  # 内部已自裁剪，状态判定与采集保持一致
    out: dict = {
        "status": res.status,
        "reason": res.reason,
        "quality": round(res.quality, 2),
        "solidity": None,
        "contour": None,
        "center": None,
        "radius": 0.0,
        "fingertips": [],
        "valleys": [],
        "guide_box": [gx0, gy0, gx1, gy1],
    }

    mask, contour = segment_hand_mask(crop, bgr_crop)
    if contour is None:
        return out
    off = np.array([gx0, gy0])
    out["contour"] = contour + off  # 平移回整帧
    out["solidity"] = round(_solidity(contour), 3)
    center, radius = palm_center(mask)
    out["center"] = (center[0] + gx0, center[1] + gy0)
    out["radius"] = radius
    dbg: dict = {}
    _finger_keypoints(contour, center, radius, dbg)
    out["fingertips"] = [p + off for p in dbg.get("fingertips", [])]
    out["valleys"] = [p + off for p in dbg.get("valleys", [])]
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
