"""PalmTemplate 数据结构与序列化（code / mask / shape / bits_per_pixel / version）。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import config


@dataclass(frozen=True)
class PalmTemplate:
    code: bytes
    mask: bytes
    height: int
    width: int
    bits_per_pixel: int
    version: str

    def pixel_count(self) -> int:
        return self.height * self.width


def pack_mask(mask: np.ndarray) -> bytes:
    """bool (H,W) → 1 bit/pixel packed bytes."""
    flat = np.asarray(mask, dtype=bool).reshape(-1)
    return np.packbits(flat).tobytes()


def unpack_mask(data: bytes, height: int, width: int) -> np.ndarray:
    n = height * width
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))[:n]
    return bits.reshape(height, width).astype(bool)


def pack_code(values: np.ndarray, bits_per_pixel: int) -> bytes:
    """整数码图 (H,W)，每像素 bits_per_pixel 位 → bytes。"""
    flat = np.asarray(values, dtype=np.uint64).reshape(-1)
    max_val = (1 << bits_per_pixel) - 1
    if flat.max(initial=0) > max_val:
        raise ValueError(f"value exceeds {bits_per_pixel}-bit range")

    out = bytearray()
    acc = 0
    nbits = 0
    for v in flat:
        acc = (acc << bits_per_pixel) | int(v)
        nbits += bits_per_pixel
        while nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
            acc &= (1 << nbits) - 1
    if nbits > 0:
        out.append((acc << (8 - nbits)) & 0xFF)
    return bytes(out)


def unpack_code(data: bytes, height: int, width: int, bits_per_pixel: int) -> np.ndarray:
    """bytes → 整数码图 (H,W)。"""
    n = height * width
    total_bits = n * bits_per_pixel
    byte_len = (total_bits + 7) // 8
    raw = np.frombuffer(data[:byte_len], dtype=np.uint8)
    bits = np.unpackbits(raw)[:total_bits]

    values = np.zeros(n, dtype=np.uint8)
    for i in range(n):
        start = i * bits_per_pixel
        chunk = bits[start : start + bits_per_pixel]
        val = 0
        for b in chunk:
            val = (val << 1) | int(b)
        values[i] = val
    return values.reshape(height, width)


def code_array(template: PalmTemplate) -> np.ndarray:
    return unpack_code(
        template.code, template.height, template.width, template.bits_per_pixel
    )


def mask_array(template: PalmTemplate) -> np.ndarray:
    return unpack_mask(template.mask, template.height, template.width)


def make_template(
    code_map: np.ndarray,
    mask: np.ndarray,
    *,
    bits_per_pixel: int | None = None,
    version: str | None = None,
) -> PalmTemplate:
    h, w = code_map.shape
    bpp = bits_per_pixel if bits_per_pixel is not None else _bits_for_version(version or config.TEMPLATE_VERSION)
    ver = version or config.TEMPLATE_VERSION
    return PalmTemplate(
        code=pack_code(code_map, bpp),
        mask=pack_mask(mask),
        height=h,
        width=w,
        bits_per_pixel=bpp,
        version=ver,
    )


def _bits_for_version(version: str) -> int:
    if version.startswith("compcode"):
        return 3
    if version.startswith("palmcode"):
        return 2
    raise ValueError(f"unknown template version: {version}")
