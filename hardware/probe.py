"""摄像头探测：逐个打开候选索引，读一帧确认真正可用并取分辨率，再释放。

故意做成同步阻塞；在 Windows 上整轮可能耗时一两秒，调用方（Flask 路由）
本身就在工作线程里，可接受。
"""

from __future__ import annotations

import time
from typing import Any

import cv2

# Windows MSMF 后端在每次失败的 grabFrame 都会打 WARN，探测死索引时刷屏。
# 只保留 ERROR 及以上。
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass


def probe_index(index: int, read_attempts: int = 8, attempt_delay: float = 0.05) -> dict[str, Any]:
    """探测单个索引，无论成功与否都会释放 capture。

    部分 USB 摄像头（尤其自动曝光）打开后头几次 read 才返回真实帧，故重试若干次。
    """
    cap = cv2.VideoCapture(index)
    try:
        if not cap.isOpened():
            return {"index": index, "available": False, "width": 0, "height": 0}

        frame = None
        for _ in range(max(1, read_attempts)):
            ok, candidate = cap.read()
            if ok and candidate is not None and candidate.size > 0:
                frame = candidate
                break
            time.sleep(attempt_delay)

        if frame is None:
            return {"index": index, "available": False, "width": 0, "height": 0}

        h, w = frame.shape[:2]
        return {"index": index, "available": True, "width": int(w), "height": int(h)}
    finally:
        cap.release()


def probe_cameras(indices: list[int] | None = None) -> list[dict[str, Any]]:
    """探测一组索引（默认 0..5），每个索引返回一条结果。"""
    if indices is None:
        indices = list(range(6))
    return [probe_index(i) for i in indices]
