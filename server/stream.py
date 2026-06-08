"""MJPEG 推流（可选叠加手掌检测几何，供前端实时查看识别结果）。"""

from __future__ import annotations

import cv2
import numpy as np
from flask import Response

from algorithm.preprocess import to_gray
from algorithm.roi import debug_geometry
from hardware.camera import Camera

# BGR 颜色
_C_CONTOUR = (0, 220, 0)      # 手掌轮廓：绿
_C_CIRCLE = (0, 200, 255)     # 掌心内切圆：黄
_C_TIP = (0, 0, 255)          # 指尖：红
_C_VALLEY = (255, 200, 0)     # 指缝：青


def _annotate(frame: np.ndarray) -> np.ndarray:
    """在帧上叠加检测几何。不烤文字（前端镜像会反字，状态文字走状态卡）。"""
    try:
        geo = debug_geometry(to_gray(frame), bgr=frame)
    except Exception:
        return frame
    # 仅当检测到指尖（张开的手掌）时才画轮廓/掌心/指缝；否则只画引导框。
    # 人脸/拳头等进入框内会被 solidity 门拒绝、无指尖，不会被画轮廓。
    if geo["fingertips"]:
        contour = geo["contour"]
        if contour is not None:
            cv2.drawContours(frame, [contour], -1, _C_CONTOUR, 2)
        center = geo["center"]
        if center is not None:
            cx, cy = int(round(center[0])), int(round(center[1]))
            r = int(round(geo["radius"]))
            if r > 0:
                cv2.circle(frame, (cx, cy), r, _C_CIRCLE, 1)
            cv2.circle(frame, (cx, cy), 4, _C_CIRCLE, -1)
        for ft in geo["fingertips"]:
            cv2.circle(frame, (int(ft[0]), int(ft[1])), 6, _C_TIP, -1)
        for v in geo["valleys"]:
            cv2.circle(frame, (int(v[0]), int(v[1])), 5, _C_VALLEY, -1)
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
