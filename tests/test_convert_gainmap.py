import numpy as np
import pytest
from PIL import ImageCms

from hdrconv.convert.gainmap import (
    _resize_gainmap_shepard,
    gainmap_to_hdr,
    hdr_to_gainmap,
)
from hdrconv.core import HDRImage


def _srgb_icc_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _synthetic_linear_hdr(peak: float = 8.0) -> np.ndarray:
    rng = np.random.default_rng(7)
    data = rng.random((64, 64, 3), dtype=np.float32)
    data[:16] *= peak  # highlights above SDR white
    return data


def test_round_trip_recovers_hdr_and_headroom():
    hdr_data = _synthetic_linear_hdr(peak=8.0)
    hdr = HDRImage(data=hdr_data, transfer_function="linear")

    gainmap_image = hdr_to_gainmap(hdr)
    reconstructed = gainmap_to_hdr(gainmap_image)

    assert gainmap_image["metadata"]["alternate_hdr_headroom"] == pytest.approx(
        np.log2(8.0), abs=1e-2
    )
    rel_error = np.abs(reconstructed["data"] - hdr_data) / (hdr_data + 1e-3)
    assert rel_error.mean() < 0.01
    assert reconstructed["transfer_function"] == "linear"


def test_round_trip_has_no_quantization_bias():
    # Truncating uint8 quantization used to give a systematic mean signed
    # error of ~-0.0146 on this round-trip; rounding brings it to ~0.
    hdr_data = _synthetic_linear_hdr(peak=8.0)
    hdr = HDRImage(data=hdr_data, transfer_function="linear")

    reconstructed = gainmap_to_hdr(hdr_to_gainmap(hdr))

    signed_error = (reconstructed["data"] - hdr_data).mean()
    assert abs(signed_error) < 1e-3


def test_baseline_quantization_rounds_to_nearest():
    baseline = np.full((4, 4, 3), 0.5, dtype=np.float32)
    hdr = HDRImage(data=baseline.copy(), transfer_function="linear")

    gainmap_image = hdr_to_gainmap(hdr, baseline=baseline)

    # eotf_inverse sRGB(0.5) * 255 = 187.516..., which must round up to 188
    # (truncation would store 187).
    assert np.all(gainmap_image["baseline"] == 188)


def test_hdr_to_gainmap_rejects_non_linear_transfer_function():
    hdr = HDRImage(
        data=np.random.rand(4, 4, 3).astype(np.float32), transfer_function="pq"
    )

    with pytest.raises(ValueError, match="Linearize"):
        hdr_to_gainmap(hdr)


def test_gainmap_to_hdr_propagates_baseline_icc():
    hdr = HDRImage(data=_synthetic_linear_hdr(), transfer_function="linear")
    baseline_icc = _srgb_icc_bytes()
    gainmap_image = hdr_to_gainmap(hdr, icc_profile=baseline_icc)

    result = gainmap_to_hdr(gainmap_image)

    assert result["icc_profile"] is baseline_icc


def test_gainmap_to_hdr_propagates_gainmap_icc_for_alternate_space():
    hdr = HDRImage(data=_synthetic_linear_hdr(), transfer_function="linear")
    baseline_icc = _srgb_icc_bytes()
    gainmap_icc = bytes(bytearray(baseline_icc))  # equal content, distinct object
    gainmap_image = hdr_to_gainmap(hdr, icc_profile=baseline_icc)
    gainmap_image["metadata"] = dict(
        gainmap_image["metadata"], use_base_colour_space=False
    )
    gainmap_image["gainmap_icc"] = gainmap_icc

    result = gainmap_to_hdr(gainmap_image)

    assert result["icc_profile"] is gainmap_icc


def test_gainmap_to_hdr_falls_back_to_baseline_icc_without_gainmap_icc():
    hdr = HDRImage(data=_synthetic_linear_hdr(), transfer_function="linear")
    baseline_icc = _srgb_icc_bytes()
    gainmap_image = hdr_to_gainmap(hdr, icc_profile=baseline_icc)
    gainmap_image["metadata"] = dict(
        gainmap_image["metadata"], use_base_colour_space=False
    )
    gainmap_image["gainmap_icc"] = None

    result = gainmap_to_hdr(gainmap_image)

    assert result["icc_profile"] is baseline_icc


def test_gainmap_to_hdr_returns_float32():
    hdr = HDRImage(data=_synthetic_linear_hdr(), transfer_function="linear")

    # No ICC profile: sRGB EOTF fallback path.
    result = gainmap_to_hdr(hdr_to_gainmap(hdr))
    assert result["data"].dtype == np.float32

    # ICC linearization path.
    result = gainmap_to_hdr(hdr_to_gainmap(hdr, icc_profile=_srgb_icc_bytes()))
    assert result["data"].dtype == np.float32


def test_gainmap_to_hdr_warns_informatively_on_bad_icc():
    hdr = HDRImage(data=_synthetic_linear_hdr(), transfer_function="linear")
    gainmap_image = hdr_to_gainmap(hdr)
    gainmap_image["baseline_icc"] = b"not an icc profile"

    with pytest.warns(UserWarning, match="falling back to sRGB EOTF"):
        result = gainmap_to_hdr(gainmap_image)

    assert result["data"].dtype == np.float32


def _shepard_reference(gainmap: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Directly-computed 4-neighbour inverse-distance-weighted resize."""
    src_h, src_w, channels = gainmap.shape
    dst_w, dst_h = size
    scale_x = dst_w / src_w
    scale_y = dst_h / src_h

    out = np.zeros((dst_h, dst_w, channels), dtype=np.float64)
    for y in range(dst_h):
        for x in range(dst_w):
            x_map = x / scale_x
            y_map = y / scale_y
            x_lower = min(int(np.floor(x_map)), src_w - 1)
            x_upper = min(x_lower + 1, src_w - 1)
            y_lower = min(int(np.floor(y_map)), src_h - 1)
            y_upper = min(y_lower + 1, src_h - 1)

            neighbours = [
                (y_lower, x_lower),
                (y_upper, x_lower),
                (y_lower, x_upper),
                (y_upper, x_upper),
            ]
            dists = [np.hypot(x_map - nx, y_map - ny) for ny, nx in neighbours]
            exact = [i for i, d in enumerate(dists) if d == 0.0]
            if exact:
                ny, nx = neighbours[exact[0]]
                out[y, x] = gainmap[ny, nx]
            else:
                weights = [1.0 / d for d in dists]
                acc = sum(
                    w * gainmap[ny, nx].astype(np.float64)
                    for w, (ny, nx) in zip(weights, neighbours)
                )
                out[y, x] = acc / sum(weights)
    return out


@pytest.mark.parametrize("size", [(13, 11), (14, 10), (3, 2)])
def test_shepard_matches_direct_idw_reference(size):
    rng = np.random.default_rng(3)
    gainmap = rng.random((5, 7, 3), dtype=np.float32) * 8 - 2

    resized = _resize_gainmap_shepard(gainmap, size)

    assert resized.dtype == np.float32
    reference = _shepard_reference(gainmap, size)
    np.testing.assert_allclose(resized, reference, rtol=1e-4, atol=1e-4)
