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


class SerialBridge(HardwareBridge):
    def __init__(self, port: str | None = None, baud: int | None = None) -> None:
        self._port = port or config.SERIAL_PORT
        self._baud = baud if baud is not None else config.SERIAL_BAUD
        self._ser = None

    def connect(self) -> None:
        import serial
        from serial.tools import list_ports

        port = self._port
        if port == "auto":
            ports = list(list_ports.comports())
            if not ports:
                raise RuntimeError("no serial port found")
            port = ports[0].device
        self._ser = serial.Serial(port, self._baud, timeout=1)
        logger.info("[SerialBridge] open %s @ %s", port, self._baud)

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


def create_bridge(use_serial: bool = False) -> HardwareBridge:
    bridge: HardwareBridge = SerialBridge() if use_serial else MockBridge()
    try:
        bridge.connect()
    except Exception as exc:
        logger.warning("hardware bridge connect failed (%s), fallback to MockBridge", exc)
        bridge = MockBridge()
        bridge.connect()
    return bridge
