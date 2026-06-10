"""基于 MediaPipe Tasks HandLandmarker 的手部关键点提取。

替代原 HSV 分割 + 距离-角度谱指缝检测：MediaPipe 直接给出 21 个手部关键点，
对光照/背景/肤色鲁棒。由四指 MCP 关键点推出 Zhang ROI 所需的两个指缝点 X1/X2。

注：py3.13 的 mediapipe wheel 只带 Tasks API（无 legacy mp.solutions），故用
HandLandmarker + data/models/hand_landmarker.task 模型文件。
"""

from __future__ import annotations

import threading

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import config

_MODEL_PATH = config.BASE_DIR / "data" / "models" / "hand_landmarker.task"

# MediaPipe Hands 21 点中的关键索引
_WRIST = 0
_INDEX_MCP = 5
_MIDDLE_MCP = 9
_RING_MCP = 13
_PINKY_MCP = 17

# HandLandmarker.detect() 对同一实例的并发调用非线程安全；Flask threaded=True
# 下多个请求（preview_status / 采集 / 调试流）会并发进入，故串行化。
_lock = threading.Lock()
_detector: vision.HandLandmarker | None = None


def _get_detector() -> vision.HandLandmarker:
    global _detector
    if _detector is None:
        # 用 buffer 而非 path：MediaPipe 原生文件加载器打不开含非 ASCII（中文）的
        # 绝对路径，改由 Python 读字节传入，绕开该限制。
        model_data = _MODEL_PATH.read_bytes()
        opts = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=model_data),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
        )
        _detector = vision.HandLandmarker.create_from_options(opts)
    return _detector


def hand_keypoints(bgr: np.ndarray):
    """检测单手，返回 (x1, x2, center, landmarks_px, hand_side) 或 None（未检到手）。

    x1 = 食指-中指根部中点，x2 = 无名-小指根部中点（Zhang ROI 的两指缝点）。
    center = 手腕点（仅用于定 ROI 的 Y 轴朝向）。坐标均为输入图像像素坐标。
    landmarks_px: (21, 2) ndarray，全部关键点像素坐标，供调试叠加。
    hand_side: "L"（左手）/ "R"（右手）。MediaPipe 返回的是镜像前的手别，
    摄像头画面左右翻转后需反转：画面中的 "Left" 实为用户右手。
    """
    if bgr is None or bgr.size == 0:
        return None
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
    with _lock:
        result = _get_detector().detect(mp_image)
    if not result.hand_landmarks:
        return None
    lm = result.hand_landmarks[0]
    pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float32)
    x1 = (pts[_INDEX_MCP] + pts[_MIDDLE_MCP]) / 2.0
    x2 = (pts[_RING_MCP] + pts[_PINKY_MCP]) / 2.0
    center = (float(pts[_WRIST][0]), float(pts[_WRIST][1]))
    # MediaPipe handedness: 摄像头已做镜像翻转，画面 "Left" 即用户左手
    mp_label = result.handedness[0][0].category_name  # "Left" / "Right"
    hand_side = "L" if mp_label == "Left" else "R"
    return x1, x2, center, pts, hand_side
