"""HardwareBridge：Mock + Serial（STM32）。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import config

logger = logging.getLogger(__name__)


class HardwareBridge(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def is_alive(self) -> bool: ...

    @abstractmethod
    def unlock(self, duration_ms: int) -> None: ...

    @abstractmethod
    def indicate(self, success: bool) -> None: ...

    @abstractmethod
    def status(self) -> dict: ...


class MockBridge(HardwareBridge):
    def connect(self) -> None:
        logger.info("[MockBridge] connected")

    def close(self) -> None:
        logger.info("[MockBridge] closed")

    def is_alive(self) -> bool:
        return True

    def unlock(self, duration_ms: int) -> None:
        logger.info("[MockBridge] UNLOCK %sms", duration_ms)

    def indicate(self, success: bool) -> None:
        logger.info("[MockBridge] %s", "OK" if success else "FAIL")

    def status(self) -> dict:
        return {
            "enabled": False,
            "connected": False,
            "port": None,
            "baudrate": None,
            "error": None,
        }


class SerialBridge(HardwareBridge):
    def __init__(self, port: str | None = None, baud: int | None = None) -> None:
        self._port = port or config.SERIAL_PORT
        self._baud = baud if baud is not None else config.SERIAL_BAUD
        self._ser = None
        self._connect_error: str | None = None

    def connect(self) -> None:
        import serial
        from serial.tools import list_ports

        port = self._port
        try:
            if port == "auto":
                ports = list(list_ports.comports())
                if not ports:
                    raise RuntimeError("no serial port found")
                port = ports[0].device
            self._ser = serial.Serial(port, self._baud, timeout=1)
            self._connect_error = None
            logger.info("[SerialBridge] open %s @ %s", port, self._baud)
        except Exception as exc:
            self._connect_error = str(exc)
            raise

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def is_alive(self) -> bool:
        if self._ser is None or not self._ser.is_open:
            return False
        try:
            self._ser.write(b"PING\n")
            line = self._ser.readline().decode("utf-8", errors="ignore").strip()
            return line == "PONG"
        except Exception:
            return False

    def _send(self, cmd: str) -> None:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("serial not connected")
        self._ser.write(cmd.encode("utf-8"))

    def unlock(self, duration_ms: int) -> None:
        self._send(f"UNLOCK {duration_ms}\n")

    def indicate(self, success: bool) -> None:
        self._send("OK\n" if success else "FAIL\n")

    def status(self) -> dict:
        connected = self._ser is not None and self._ser.is_open
        return {
            "enabled": True,
            "connected": connected,
            "port": self._port,
            "baudrate": self._baud,
            "error": None if connected else (self._connect_error or "串口未连接"),
        }


def create_bridge(use_serial: bool = False) -> HardwareBridge:
    bridge: HardwareBridge = SerialBridge() if use_serial else MockBridge()
    try:
        bridge.connect()
    except Exception as exc:
        if use_serial:
            # 不降级，保留 SerialBridge 让前端显示"连接失败"
            logger.warning("serial connect failed: %s", exc)
        else:
            bridge = MockBridge()
            bridge.connect()
    return bridge
