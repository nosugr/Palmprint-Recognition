"""MJPEG 推流。"""

from __future__ import annotations

import cv2
from flask import Response

from hardware.camera import Camera


def mjpeg_generator(camera: Camera):
    while True:
        frame = camera.read()
        if frame is None:
            continue
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )


def video_feed_response(camera: Camera) -> Response:
    return Response(
        mjpeg_generator(camera),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
