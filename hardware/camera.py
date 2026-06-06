"""Camera 抽象与实现。"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np


class Camera(ABC):
    @abstractmethod
    def read(self) -> np.ndarray | None:
        """返回 BGR 帧；失败返回 None。"""

    @abstractmethod
    def is_open(self) -> bool:
        ...

    def release(self) -> None:
        pass


class WebcamCamera(Camera):
    def __init__(self, device: int = 0) -> None:
        self._cap = cv2.VideoCapture(device)
        self._lock = threading.Lock()

    def read(self) -> np.ndarray | None:
        with self._lock:
            if not self._cap.isOpened():
                return None
            ok, frame = self._cap.read()
            return frame if ok else None

    def is_open(self) -> bool:
        return self._cap.isOpened()

    def release(self) -> None:
        with self._lock:
            if self._cap.isOpened():
                self._cap.release()


class FolderCamera(Camera):
    """无摄像头时从目录循环读图（开发/测试）。"""

    def __init__(self, folder: Path | str) -> None:
        folder = Path(folder)
        suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        self._paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in suffixes)
        self._index = 0
        self._lock = threading.Lock()
        if not self._paths:
            raise ValueError(f"no images in {folder}")

    def read(self) -> np.ndarray | None:
        with self._lock:
            path = self._paths[self._index % len(self._paths)]
            self._index += 1
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        return img

    def is_open(self) -> bool:
        return bool(self._paths)


def create_camera(prefer_webcam: bool = True, fallback_dir: Path | str | None = None) -> Camera:
    if prefer_webcam:
        cam = WebcamCamera(0)
        if cam.is_open():
            return cam
        cam.release()
    if fallback_dir is not None:
        return FolderCamera(fallback_dir)
    raise RuntimeError("no camera available and no fallback image folder")
