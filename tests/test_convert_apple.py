import colour
import numpy as np
import pytest

from hdrconv.convert.apple import apple_heic_to_hdr
from hdrconv.convert.gainmap import hdr_to_gainmap


def _make_data(gainmap: np.ndarray) -> dict:
    base = np.full((8, 8, 3), 128, dtype=np.uint8)
    return {"base": base, "gainmap": gainmap, "headroom": 2.0}


def _linearize_scalar(x: float) -> float:
    """Run a single normalized value through the module's sRGB linearization."""
    code = int(round(x * 255.0))
    base = np.full((2, 2, 3), code, dtype=np.uint8)
    gainmap = np.zeros((2, 2), dtype=np.uint8)
    hdr = apple_heic_to_hdr({"base": base, "gainmap": gainmap, "headroom": 2.0})
    return float(hdr["data"][0, 0, 0])


def test_srgb_white_maps_to_exactly_one():
    assert _linearize_scalar(1.0) == pytest.approx(1.0, abs=1e-7)


def test_srgb_matches_colour_eotf_across_range():
    # Probe every uint8 code value, which covers [0, 1] at the input
    # granularity the function actually receives.
    codes = np.arange(256, dtype=np.uint8)
    base = np.stack([codes] * 3, axis=-1)[np.newaxis, ...]  # (1, 256, 3)
    gainmap = np.zeros((1, 256), dtype=np.uint8)
    hdr = apple_heic_to_hdr({"base": base, "gainmap": gainmap, "headroom": 2.0})
    got = hdr["data"][0, :, 0]
    expected = colour.eotf(codes.astype(np.float64) / 255.0, "sRGB")
    np.testing.assert_allclose(got, expected, atol=1e-6)


def test_srgb_continuity_at_threshold():
    # The IEC 61966-2-1 threshold is 0.04045; the two branches must agree
    # there (no jump that would band smooth gradients).
    threshold = 0.04045
    linear_branch = threshold / 12.92
    power_branch = ((threshold + 0.055) / 1.055) ** 2.4
    assert linear_branch == pytest.approx(power_branch, abs=1e-5)
    # And the function itself must be monotonic through nearby code values.
    values = [_linearize_scalar(c / 255.0) for c in range(8, 14)]
    assert all(b > a for a, b in zip(values, values[1:]))


def test_gainmap_2d_shape_accepted():
    gainmap = np.zeros((4, 4), dtype=np.uint8)
    hdr = apple_heic_to_hdr(_make_data(gainmap))
    assert hdr["data"].shape == (8, 8, 3)


def test_gainmap_hw1_shape_accepted():
    gainmap = np.zeros((4, 4, 1), dtype=np.uint8)
    hdr = apple_heic_to_hdr(_make_data(gainmap))
    assert hdr["data"].shape == (8, 8, 3)


def test_gainmap_hw1_matches_2d_result():
    rng = np.random.default_rng(0)
    gainmap_2d = rng.integers(0, 256, size=(4, 4), dtype=np.uint8)
    hdr_2d = apple_heic_to_hdr(_make_data(gainmap_2d))
    hdr_3d = apple_heic_to_hdr(_make_data(gainmap_2d[..., np.newaxis]))
    np.testing.assert_array_equal(hdr_2d["data"], hdr_3d["data"])


def test_source_icc_propagates_to_generated_gainmap():
    icc_profile = b"display-p3-profile"
    hdr = apple_heic_to_hdr(
        {**_make_data(np.zeros((4, 4), dtype=np.uint8)), "icc_profile": icc_profile}
    )

    assert hdr["icc_profile"] == icc_profile
    gainmap = hdr_to_gainmap(hdr)
    assert gainmap["baseline_icc"] == icc_profile
    assert gainmap["gainmap_icc"] == icc_profile
