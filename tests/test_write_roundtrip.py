import numpy as np
import pytest

from hdrconv.core import GainmapImage, GainmapMetadata
from hdrconv.io._jpeg import build_segment, build_icc_segments
from hdrconv.io.iso21496 import (
    _extract_icc,
    _split_mpf_container,
    _yield_jpeg_segments,
    read_21496,
    write_21496,
)
from hdrconv.io.ultrahdr import read_ultrahdr, write_ultrahdr


def _fake_icc(size: int) -> bytes:
    # Only the write path is exercised, so any opaque bytes work as a profile.
    return bytes(range(256)) * (size // 256 + 1)


def _sample_image(gainmap_channels: int = 1) -> GainmapImage:
    rng = np.random.default_rng(0)
    baseline = (rng.random((32, 48, 3)) * 255).astype(np.uint8)
    gainmap = (rng.random((16, 24, gainmap_channels)) * 255).astype(np.uint8)
    metadata = GainmapMetadata(
        minimum_version=0,
        writer_version=0,
        baseline_hdr_headroom=1.0,
        alternate_hdr_headroom=4.0,
        is_multichannel=gainmap_channels == 3,
        use_base_colour_space=True,
        gainmap_min=(0.0,) * gainmap_channels,
        gainmap_max=(2.0,) * gainmap_channels,
        gainmap_gamma=(1.0,) * gainmap_channels,
        baseline_offset=(0.015625,) * gainmap_channels,
        alternate_offset=(0.015625,) * gainmap_channels,
    )
    return GainmapImage(
        baseline=baseline,
        gainmap=gainmap,
        metadata=metadata,
        baseline_icc=_fake_icc(600),
        gainmap_icc=None,
    )


def test_write_21496_roundtrip(tmp_path):
    data = _sample_image()
    path = str(tmp_path / "out.jpg")

    write_21496(data, path)
    back = read_21496(path)

    assert back["baseline"].shape == (32, 48, 3)
    assert back["gainmap"].shape[:2] == (16, 24)
    assert back["baseline_icc"] == data["baseline_icc"]
    assert back["gainmap_icc"] is None
    meta = back["metadata"]
    assert meta["alternate_hdr_headroom"] == pytest.approx(4.0)
    assert meta["gainmap_max"][0] == pytest.approx(2.0)
    assert meta["baseline_offset"][0] == pytest.approx(0.015625)


def test_write_21496_mpf_split_and_streams_decode(tmp_path):
    data = _sample_image()
    path = str(tmp_path / "out.jpg")
    write_21496(data, path)

    with open(path, "rb") as f:
        blob = f.read()
    primary, gainmap = _split_mpf_container(blob)

    # MPF offsets must split the file exactly at the gainmap SOI.
    assert primary + gainmap == blob
    assert gainmap[:2] == b"\xff\xd8"
    # JFIF APP0 must remain the first segment of each stream.
    assert next(_yield_jpeg_segments(primary))[0] == 0xFFE0
    assert next(_yield_jpeg_segments(gainmap))[0] == 0xFFE0


def test_write_21496_chunked_icc_roundtrip(tmp_path):
    data = _sample_image()
    data["baseline_icc"] = _fake_icc(150_000)  # forces 3 APP2 chunks
    path = str(tmp_path / "out.jpg")

    write_21496(data, path)

    with open(path, "rb") as f:
        primary, _ = _split_mpf_container(f.read())
    segments = list(_yield_jpeg_segments(primary))
    icc_segments = [
        p for c, p in segments if c == 0xFFE2 and p.startswith(b"ICC_PROFILE\x00")
    ]
    assert len(icc_segments) == 3
    assert _extract_icc(segments) == data["baseline_icc"]

    back = read_21496(path)
    assert back["baseline_icc"] == data["baseline_icc"]


def test_write_21496_multichannel_and_float_inputs(tmp_path):
    data = _sample_image(gainmap_channels=3)
    data["baseline"] = data["baseline"].astype(np.float32) / 255.0
    path = str(tmp_path / "out.jpg")

    write_21496(data, path)
    back = read_21496(path)

    assert back["baseline"].shape == (32, 48, 3)
    assert back["gainmap"].shape == (16, 24, 3)


def test_write_21496_rgba_and_noncontiguous_inputs(tmp_path):
    rng = np.random.default_rng(1)
    data = _sample_image()
    data["baseline"] = (rng.random((32, 48, 4)) * 255).astype(np.uint8)  # RGBA
    data["gainmap"] = np.asfortranarray(data["gainmap"])  # non-contiguous
    path = str(tmp_path / "out.jpg")

    write_21496(data, path)
    back = read_21496(path)

    assert back["baseline"].shape == (32, 48, 3)  # alpha dropped
    assert back["gainmap"].shape[:2] == (16, 24)


def test_write_ultrahdr_roundtrip(tmp_path):
    data = _sample_image()
    data["gainmap_icc"] = _fake_icc(400)
    path = str(tmp_path / "out.jpg")

    write_ultrahdr(data, path)
    back = read_ultrahdr(path)

    assert back["baseline"].shape == (32, 48, 3)
    assert back["baseline_icc"] == data["baseline_icc"]
    assert back["gainmap_icc"] == data["gainmap_icc"]
    assert back["metadata"]["alternate_hdr_headroom"] == pytest.approx(4.0)


def test_write_rescales_deep_integer_inputs(tmp_path):
    # Readers (ISOBMFF, iOS screenshot) can return >8-bit integer arrays;
    # writers must rescale by the recorded bit depth instead of clipping.
    # Smooth gradients keep JPEG error tiny so the assertion discriminates:
    # a clipping regression yields mean errors of ~67 codes.
    data = _sample_image()
    grad = np.linspace(0, 255, 48, dtype=np.uint8)
    base8 = np.stack([np.tile(grad, (32, 1))] * 3, axis=-1)
    gm8 = np.tile(np.linspace(30, 220, 24, dtype=np.uint8), (16, 1))[:, :, None]
    data["baseline"] = base8.astype(np.uint16) << 8 | base8  # full-range 16-bit
    data["gainmap"] = gm8.astype(np.uint16) << 2  # 10-bit range
    data["baseline_bit_depth"] = 16
    data["gainmap_bit_depth"] = 10
    path = str(tmp_path / "out.jpg")

    write_21496(data, path)
    back = read_21496(path)

    assert np.abs(back["baseline"].astype(int) - base8.astype(int)).mean() < 3
    gm_back = back["gainmap"][:, :, 0].astype(int)
    assert np.abs(gm_back - gm8[:, :, 0].astype(int)).mean() < 3
    assert back["baseline"].max() > 200  # not clipped to a saturated mess

    write_ultrahdr(data, path)
    uback = read_ultrahdr(path)
    assert np.abs(uback["baseline"].astype(int) - base8.astype(int)).mean() < 3


def test_build_segment_rejects_oversized_payload():
    with pytest.raises(ValueError, match="payload too large"):
        build_segment(0xFFE2, b"x" * 65534)


def test_build_icc_segments_empty_input():
    assert build_icc_segments(None) == []
    assert build_icc_segments(b"") == []
