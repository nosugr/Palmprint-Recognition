import numpy as np

from algorithm.encode import encode
from algorithm.template import code_array, mask_array


def _synthetic_roi(size: int = 128) -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:size, 0:size]
    roi = ((np.sin(x / 8) + np.cos(y / 6)) * 60 + 128).astype(np.uint8)
    mask = np.ones((size, size), dtype=bool)
    return roi, mask


def test_encode_reproducible():
    roi, mask = _synthetic_roi()
    a = encode(roi, mask)
    b = encode(roi, mask)
    assert a.code == b.code
    assert a.mask == b.mask
    assert a.version == "compcode-v3"
    assert a.bits_per_pixel == 3


def test_encode_roundtrip_pack_unpack():
    roi, mask = _synthetic_roi(64)
    tmpl = encode(roi, mask)
    code = code_array(tmpl)
    m = mask_array(tmpl)
    assert code.shape == (64, 64)
    assert code.max() <= 5
    assert m.shape == (64, 64)
