"""MJPEG 推流（可选叠加手掌检测几何，供前端实时查看识别结果）。"""

from __future__ import annotations

import cv2
import numpy as np
from flask import Response

from algorithm.preprocess import to_gray
from algorithm.roi import debug_geometry
from hardware.camera import Camera

# BGR 颜色
_C_LANDMARK = (0, 220, 0)     # 手部关键点：绿
_C_KEYPOINT = (0, 0, 255)     # 指缝点 X1/X2：红


def _annotate(frame: np.ndarray) -> np.ndarray:
    """在帧上叠加检测几何。不烤文字（前端镜像会反字，状态文字走状态卡）。"""
    try:
        geo = debug_geometry(to_gray(frame), bgr=frame)
    except Exception:
        return frame
    # 检测到手时画 21 个 MediaPipe 关键点 + 两个指缝点 X1/X2；否则只画引导框。
    for p in geo["landmarks"]:
        cv2.circle(frame, (int(p[0]), int(p[1])), 3, _C_LANDMARK, -1)
    for key in ("x1", "x2"):
        kp = geo.get(key)
        if kp is not None:
            cv2.circle(frame, (int(kp[0]), int(kp[1])), 6, _C_KEYPOINT, -1)
    # 画出引导框矩形，方便目视核对前后端框是否重合
    gb = geo.get("guide_box")
    if gb:
        cv2.rectangle(frame, (gb[0], gb[1]), (gb[2], gb[3]), (180, 180, 180), 1)
    return frame


def mjpeg_generator(camera: Camera, debug: bool = False):
    while True:
        frame = camera.read()
        if frame is None:
            continue
        if debug:
            frame = _annotate(frame)
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )


def video_feed_response(camera: Camera, debug: bool = False) -> Response:
    return Response(
        mjpeg_generator(camera, debug=debug),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
