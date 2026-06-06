import numpy as np

from algorithm.encode import encode
from algorithm.matcher import match_distance
from algorithm.template import code_array, make_template


def _synthetic_roi(size: int = 128) -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:size, 0:size]
    roi = ((np.sin(x / 8) + np.cos(y / 6)) * 60 + 128).astype(np.uint8)
    mask = np.ones((size, size), dtype=bool)
    return roi, mask


def test_same_template_zero_distance():
    roi, mask = _synthetic_roi(64)
    tmpl = encode(roi, mask)
    assert match_distance(tmpl, tmpl) == 0.0


def test_genuine_closer_than_impostor():
    roi1, mask1 = _synthetic_roi(64)
    rng = np.random.default_rng(99)
    roi2 = rng.integers(0, 256, (64, 64), dtype=np.uint8)
    mask2 = np.ones((64, 64), dtype=bool)

    t1 = encode(roi1, mask1)
    t2 = encode(roi1, mask1)  # 同人
    t3 = encode(roi2, mask2)  # 不同纹理

    d_genuine = match_distance(t1, t2)
    d_impostor = match_distance(t1, t3)
    assert d_genuine < d_impostor


def test_shift_matching_reduces_distance():
    roi, mask = _synthetic_roi(64)
    base = encode(roi, mask)

    code = code_array(base)
    shifted_code = np.zeros_like(code)
    shifted_code[1:, 1:] = code[:-1, :-1]
    shifted = make_template(shifted_code, mask)

    d_no_shift = match_distance(base, shifted, max_shift=0)
    d_with_shift = match_distance(base, shifted, max_shift=2)
    assert d_with_shift <= d_no_shift
