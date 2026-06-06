import numpy as np

from algorithm.preprocess import preprocess


def test_preprocess_shape_and_dtype():
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    roi, mask = preprocess(img, roi_size=128)
    assert roi.shape == (128, 128)
    assert roi.dtype == np.uint8
    assert mask.shape == (128, 128)
    assert mask.dtype == bool


def test_preprocess_mask_excludes_extreme_pixels():
    img = np.full((200, 200, 3), 10, dtype=np.uint8)
    roi, mask = preprocess(img, roi_size=64)
    assert mask.sum() == 0

    img2 = np.full((200, 200, 3), 128, dtype=np.uint8)
    roi2, mask2 = preprocess(img2, roi_size=64)
    assert mask2.all()
