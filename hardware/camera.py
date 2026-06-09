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
        self._index = device
        self._cap = cv2.VideoCapture(device)
        self._lock = threading.Lock()
        # isOpened() 在 Windows 上常假阳性：设备号被占用但仍报 opened，read 却永远失败。
        # 开后真读一帧（带重试，兼容 USB 相机的几百毫秒预热）才算可用。
        self._usable = self._cap.isOpened() and self._probe()

    def _probe(self, attempts: int = 8, delay: float = 0.05) -> bool:
        for _ in range(attempts):
            ok, frame = self._cap.read()
            if ok and frame is not None and frame.size > 0:
                return True
            time.sleep(delay)
        return False

    @property
    def index(self) -> int:
        return self._index

    def read(self) -> np.ndarray | None:
        with self._lock:
            if not self._cap.isOpened():
                return None
            ok, frame = self._cap.read()
            return frame if ok else None

    def is_open(self) -> bool:
        return self._cap.isOpened() and self._usable

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


class SwitchableCamera(Camera):
    """对外稳定的摄像头对象：内部持有真实摄像头，可在运行时热切换设备。

    视频流 / 识别 / 健康检查始终引用同一个 SwitchableCamera，切换设备时只换它
    内部的真实摄像头，故正在播放的 MJPEG 流也会即时切到新摄像头，外部无需重新取对象。
    """

    def __init__(self, inner: Camera, index: int | None) -> None:
        self._inner = inner
        self._index = index
        self._lock = threading.Lock()

    @property
    def current_index(self) -> int | None:
        return self._index

    def read(self) -> np.ndarray | None:
        with self._lock:
            return self._inner.read()

    def is_open(self) -> bool:
        with self._lock:
            return self._inner.is_open()

    def switch(self, index: int) -> bool:
        """切换到指定设备号。成功返回 True；失败保留原摄像头并返回 False。"""
        new = WebcamCamera(index)
        if not new.is_open():
            new.release()
            return False
        # 先在锁外打开（慢），仅在锁内做引用替换（快），再释放旧的。
        with self._lock:
            old = self._inner
            self._inner = new
            self._index = index
        old.release()
        return True

    def release(self) -> None:
        with self._lock:
            self._inner.release()


def create_camera(
    prefer_webcam: bool = True,
    fallback_dir: Path | str | None = None,
    index: int = 0,
) -> SwitchableCamera:
    if prefer_webcam:
        cam = WebcamCamera(index)
        if cam.is_open():
            return SwitchableCamera(cam, index)
        cam.release()
    if fallback_dir is not None:
        # 回退到图片目录；current_index 为 None，之后仍可通过 switch() 切到真实摄像头。
        return SwitchableCamera(FolderCamera(fallback_dir), None)
    raise RuntimeError("no camera available and no fallback image folder")
