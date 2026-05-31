import numpy as np
import pytest

from hdrconv.convert.gainmap import _resize_gainmap_array


def test_resize_gainmap_shepard_matches_four_neighbour_idw():
    gainmap = np.array(
        [
            [[0.0], [1.0]],
            [[2.0], [3.0]],
        ],
        dtype=np.float32,
    )

    resized = _resize_gainmap_array(gainmap, (4, 4), method="shepard")

    assert resized.shape == (4, 4, 1)
    assert resized[0, 0, 0] == pytest.approx(0.0)
    assert resized[0, 2, 0] == pytest.approx(1.0)
    assert resized[2, 0, 0] == pytest.approx(2.0)
    assert resized[2, 2, 0] == pytest.approx(3.0)
    assert resized[1, 1, 0] == pytest.approx(1.5)
    assert resized[0, 1, 0] == pytest.approx(1.118034, abs=1e-6)
    assert resized[1, 0, 0] == pytest.approx(1.309017, abs=1e-6)


def test_resize_gainmap_lanczos4_remains_available():
    gainmap = np.arange(12, dtype=np.float32).reshape(2, 2, 3)

    resized = _resize_gainmap_array(gainmap, (4, 4), method="lanczos4")

    assert resized.shape == (4, 4, 3)
    assert resized.dtype == np.float32


def test_resize_gainmap_rejects_unknown_method():
    gainmap = np.zeros((2, 2, 1), dtype=np.float32)

    with pytest.raises(ValueError, match="Invalid gainmap resize method"):
        _resize_gainmap_array(gainmap, (4, 4), method="unsupported")
