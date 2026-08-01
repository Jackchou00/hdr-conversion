import hashlib
import shutil
from pathlib import Path

import numpy as np
import pillow_heif
import pytest
from PIL import Image

import hdrconv.io.apple_heic as apple_heic_io
import hdrconv.io.ios_hdr_screenshot as ios_io
from hdrconv.identify.apple_heic import has_gain_map
from hdrconv.io.apple_heic import (
    _heif_image_to_uint8_array,
    get_headroom,
    read_apple_heic,
    read_base_and_gain_map,
)
from hdrconv.io.ios_hdr_screenshot import (
    _split_ids_into_groups,
    read_ios_hdr_screenshot,
)

IMAGES_DIR = Path(__file__).parent.parent / "images"
APPLE_HEIC = IMAGES_DIR / "appleheic.HEIC"
IOS_SCREENSHOT = IMAGES_DIR / "ioshdrscreenshot.HEIC"

needs_apple_heic = pytest.mark.skipif(
    not APPLE_HEIC.exists(), reason="appleheic.HEIC sample not available"
)
needs_ios_screenshot = pytest.mark.skipif(
    not IOS_SCREENSHOT.exists(), reason="ioshdrscreenshot.HEIC sample not available"
)
needs_external_tools = pytest.mark.skipif(
    shutil.which("MP4Box") is None or shutil.which("ffmpeg") is None,
    reason="MP4Box and ffmpeg are required",
)


class _FakeHeifImage:
    """Minimal stand-in for a pillow_heif image (mode/size/data/stride)."""

    def __init__(self, mode, size, data, stride):
        self.mode = mode
        self.size = size
        self.data = data
        self.stride = stride


def _make_16bit_fake(mode, channels, width=4, height=3, pad_samples=2):
    rng = np.random.default_rng(7)
    row_samples = width * channels
    padded = rng.integers(
        0, 65536, size=(height, row_samples + pad_samples), dtype=np.uint16
    )
    stride = (row_samples + pad_samples) * 2
    image = _FakeHeifImage(mode, (width, height), padded.tobytes(), stride)
    expected16 = padded[:, :row_samples]
    if channels > 1:
        expected16 = expected16.reshape(height, width, channels)
    return image, (expected16 >> 8).astype(np.uint8)


def test_heif_rgb16_downshifts_to_uint8():
    image, expected = _make_16bit_fake("RGB;16", 3)
    result = _heif_image_to_uint8_array(image)
    assert result.dtype == np.uint8
    assert result.shape == (3, 4, 3)
    np.testing.assert_array_equal(result, expected)


def test_heif_rgba16_downshifts_to_uint8():
    image, expected = _make_16bit_fake("RGBA;16", 4)
    result = _heif_image_to_uint8_array(image)
    assert result.dtype == np.uint8
    assert result.shape == (3, 4, 4)
    np.testing.assert_array_equal(result, expected)


def test_heif_l16_downshifts_to_uint8():
    image, expected = _make_16bit_fake("L;16", 1)
    result = _heif_image_to_uint8_array(image)
    assert result.dtype == np.uint8
    assert result.shape == (3, 4)
    np.testing.assert_array_equal(result, expected)


def test_heif_unsupported_16bit_mode_raises():
    image = _FakeHeifImage("I;16", (2, 2), b"\x00" * 8, 4)
    with pytest.raises(ValueError, match="Unsupported HEIF image mode"):
        _heif_image_to_uint8_array(image)


def test_heif_8bit_mode_matches_pil_path():
    # 8-bit modes must keep the original PIL.Image.frombytes behavior.
    rng = np.random.default_rng(3)
    width, height, pad = 5, 4, 3
    padded = rng.integers(0, 256, size=(height, width * 3 + pad), dtype=np.uint8)
    image = _FakeHeifImage("RGB", (width, height), padded.tobytes(), width * 3 + pad)
    expected = np.array(
        Image.frombytes("RGB", (width, height), padded.tobytes(), "raw", "RGB", width * 3 + pad)
    )
    np.testing.assert_array_equal(_heif_image_to_uint8_array(image), expected)


def test_read_10bit_heic_does_not_crash(tmp_path):
    # A 10-bit HEIC decodes to mode 'RGB;16'; read_base_and_gain_map used to
    # crash in Image.frombytes ("unrecognized image mode").
    rng = np.random.default_rng(0)
    arr16 = rng.integers(0, 1024, size=(64, 80, 3), dtype=np.uint16) << 6
    heif_file = pillow_heif.from_bytes(
        mode="RGB;16", size=(80, 64), data=arr16.tobytes()
    )
    path = str(tmp_path / "rgb10.heic")
    heif_file.save(path, quality=-1)

    decoded = pillow_heif.read_heif(path, convert_hdr_to_8bit=False)
    assert decoded.mode == "RGB;16"

    base, gain_map = read_base_and_gain_map(path)
    assert base.dtype == np.uint8
    assert base.shape == (64, 80, 3)
    assert gain_map is None

    # The downshift must agree with pillow_heif's own 8-bit conversion
    # (small tolerance: pillow_heif rounds while >>8 truncates).
    decoded8 = pillow_heif.read_heif(path, convert_hdr_to_8bit=True)
    arr8 = _heif_image_to_uint8_array(decoded8)
    assert np.abs(base.astype(int) - arr8.astype(int)).max() <= 2


@needs_apple_heic
def test_read_apple_heic_8bit_regression():
    # 8-bit files must produce byte-identical results to the pre-fix reader.
    base, gain_map = read_base_and_gain_map(str(APPLE_HEIC))
    assert base.dtype == np.uint8
    assert base.shape == (4284, 5712, 3)
    assert hashlib.md5(base.tobytes()).hexdigest() == "47bb8e4a650c10ef79737c180e5a22df"
    assert gain_map.dtype == np.uint8
    assert gain_map.shape == (2142, 2856)
    assert (
        hashlib.md5(gain_map.tobytes()).hexdigest()
        == "ae2c957ddbe61e91af8b8ea10e8f207f"
    )


@needs_apple_heic
def test_read_apple_heic_keeps_embedded_icc_profile():
    data = read_apple_heic(str(APPLE_HEIC))
    expected = pillow_heif.read_heif(str(APPLE_HEIC)).info["icc_profile"]
    assert data["icc_profile"] == expected


@needs_apple_heic
@needs_ios_screenshot
def test_has_gain_map_booleans_unchanged():
    assert has_gain_map(str(APPLE_HEIC)) is True
    assert has_gain_map(str(IOS_SCREENSHOT)) is False


def _patch_exiftool(monkeypatch, metadata):
    class FakeHelper:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_tags(self, file_path, tags):
            return [dict(metadata)]

    monkeypatch.setattr(apple_heic_io, "ExifToolHelper", FakeHelper)
    monkeypatch.setattr(apple_heic_io, "_check_exiftool_installed", lambda: None)


def test_get_headroom_makernote_preferred_falls_back_to_xmp(monkeypatch):
    _patch_exiftool(monkeypatch, {"XMP:HDRGainMapHeadroom": 4.0})
    assert get_headroom("dummy.heic", use_makernote=True) == pytest.approx(4.0)


def test_get_headroom_makernote_used_when_present(monkeypatch):
    _patch_exiftool(
        monkeypatch,
        {
            "XMP:HDRGainMapHeadroom": 4.0,
            "MakerNotes:HDRHeadroom": 1.5,
            "MakerNotes:HDRGain": 0.5,
        },
    )
    expected = 2.0 ** (-0.303 * 0.5 + 2.303)
    assert get_headroom("dummy.heic", use_makernote=True) == pytest.approx(expected)


def test_get_headroom_raises_when_no_metadata(monkeypatch):
    _patch_exiftool(monkeypatch, {})
    with pytest.raises(ValueError, match="Cannot extract HDR headroom"):
        get_headroom("dummy.heic", use_makernote=True)


def test_split_ids_into_groups():
    assert _split_ids_into_groups([1, 2, 3, 7, 8]) == [[1, 2, 3], [7, 8]]
    assert _split_ids_into_groups([1, 2, 3]) == [[1, 2, 3]]
    assert _split_ids_into_groups([]) == []


def test_single_group_error_names_group_sizes(monkeypatch, tmp_path):
    dummy = tmp_path / "dummy.heic"
    dummy.write_bytes(b"")
    monkeypatch.setattr(ios_io, "_check_dependencies", lambda: (True, []))
    monkeypatch.setattr(ios_io, "_get_hvc1_ids", lambda path: [1, 2, 3])
    with pytest.raises(ValueError, match=r"1 group\(s\) with sizes \[3\]"):
        read_ios_hdr_screenshot(str(dummy))


@needs_ios_screenshot
@needs_external_tools
def test_read_ios_hdr_screenshot_full_precision():
    data = read_ios_hdr_screenshot(str(IOS_SCREENSHOT))

    assert data["baseline"].dtype == np.uint16
    assert data["gainmap"].dtype == np.uint16
    assert data["baseline"].shape == (2556, 1179, 3)
    assert data["gainmap"].shape == (2556, 1179, 3)
    # Declared bit depth must match the true depth of the arrays.
    assert data["baseline_bit_depth"] == 16
    assert data["gainmap_bit_depth"] == 16

    headroom = data["metadata"]["alternate_hdr_headroom"]
    assert headroom == pytest.approx(1.5374, abs=1e-3)


@needs_ios_screenshot
@needs_external_tools
def test_ios_hdr_screenshot_reconstruction_peak():
    import warnings

    from hdrconv.convert import gainmap_to_hdr

    data = read_ios_hdr_screenshot(str(IOS_SCREENSHOT))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hdr = gainmap_to_hdr(data)

    expected_peak = 2.0 ** data["metadata"]["alternate_hdr_headroom"]
    assert float(hdr["data"].max()) == pytest.approx(expected_peak, rel=0.05)
