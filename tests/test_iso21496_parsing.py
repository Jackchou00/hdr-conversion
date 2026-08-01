import shutil
import struct
import warnings

import numpy as np
import pytest

from hdrconv.core import GainmapImage, GainmapMetadata
from hdrconv.io import iso21496
from hdrconv.io.iso21496 import (
    ISO21496_URN,
    ISO21496_URN_ALT,
    MPF_LABEL,
    _align_uint16_to_bit_depth,
    _encode_iso21496_metadata,
    _extract_icc,
    _parse_iso21496_metadata,
    _probe_video_item,
    _read_rational,
    _split_mpf_container,
    write_21496,
)

APP2 = 0xFFE2


def _metadata_body(channels: int = 1) -> bytes:
    """Build a raw ISO 21496-1 binary metadata block (no URN prefix)."""
    body = bytearray()
    flags = 0x80 if channels == 3 else 0x00
    body += struct.pack(">HHB", 0, 0, flags)  # min_ver=0 -> first byte is 0x00
    body += struct.pack(">II", 0, 1)  # baseline headroom
    body += struct.pack(">II", 4, 1)  # alternate headroom
    for _ in range(channels):
        body += struct.pack(">iI", -1, 2)  # min
        body += struct.pack(">iI", 5, 2)  # max
        body += struct.pack(">II", 1, 1)  # gamma
        body += struct.pack(">iI", 1, 64)  # base offset
        body += struct.pack(">iI", 1, 64)  # alt offset
    return bytes(body)


def _sample_image(gainmap_channels: int = 1) -> GainmapImage:
    rng = np.random.default_rng(0)
    return GainmapImage(
        baseline=(rng.random((32, 48, 3)) * 255).astype(np.uint8),
        gainmap=(rng.random((16, 24, gainmap_channels)) * 255).astype(np.uint8),
        metadata=GainmapMetadata(
            baseline_hdr_headroom=0.0,
            alternate_hdr_headroom=4.0,
            is_multichannel=gainmap_channels == 3,
            gainmap_min=(0.0,) * gainmap_channels,
            gainmap_max=(2.0,) * gainmap_channels,
            gainmap_gamma=(1.0,) * gainmap_channels,
            baseline_offset=(0.015625,) * gainmap_channels,
            alternate_offset=(0.015625,) * gainmap_channels,
        ),
        baseline_icc=None,
        gainmap_icc=None,
    )


# -----------------------------------------------------------------------------
# Null-less URN (confirmed #0)
# -----------------------------------------------------------------------------


def test_nullless_urn_with_leading_zero_metadata_byte_parses():
    meta = _parse_iso21496_metadata(ISO21496_URN_ALT + _metadata_body())
    assert meta["alternate_hdr_headroom"] == pytest.approx(4.0)
    assert meta["gainmap_min"] == (pytest.approx(-0.5),)


def test_nullless_urn_multichannel_parses():
    meta = _parse_iso21496_metadata(ISO21496_URN_ALT + _metadata_body(3))
    assert meta["is_multichannel"] is True
    assert meta["gainmap_max"] == (2.5, 2.5, 2.5)


def test_null_terminated_urn_still_parses():
    for channels in (1, 3):
        meta = _parse_iso21496_metadata(ISO21496_URN + _metadata_body(channels))
        assert meta["alternate_hdr_headroom"] == pytest.approx(4.0)


# -----------------------------------------------------------------------------
# MPF split with fill bytes (confirmed #1)
# -----------------------------------------------------------------------------


def test_split_mpf_container_with_fill_byte_before_marker(tmp_path):
    path = str(tmp_path / "out.jpg")
    write_21496(_sample_image(), path)
    with open(path, "rb") as f:
        blob = f.read()

    # JPEG permits 0xFF fill bytes before any marker; insert one before MPF APP2.
    marker_pos = blob.find(MPF_LABEL) - 4  # marker(2) + length(2)
    assert blob[marker_pos : marker_pos + 2] == b"\xff\xe2"
    padded = blob[:marker_pos] + b"\xff" + blob[marker_pos:]

    primary, gainmap = _split_mpf_container(padded)
    assert primary + gainmap == padded
    assert gainmap[:2] == b"\xff\xd8"

    # Unpadded split stays exact.
    primary0, gainmap0 = _split_mpf_container(blob)
    assert primary0 + gainmap0 == blob
    assert gainmap0 == gainmap


# -----------------------------------------------------------------------------
# Encoder channel count derived from data (confirmed #3)
# -----------------------------------------------------------------------------


def test_encode_three_values_without_flag_keeps_all_channels():
    meta = GainmapMetadata(
        baseline_hdr_headroom=0.0,
        alternate_hdr_headroom=4.0,
        gainmap_min=(-0.5, -0.25, 0.0),
        gainmap_max=(2.0, 2.0, 2.0),
        gainmap_gamma=(1.0, 1.0, 1.0),
        baseline_offset=(0.0, 0.0, 0.0),
        alternate_offset=(0.0, 0.0, 0.0),
    )
    back = _parse_iso21496_metadata(_encode_iso21496_metadata(meta))
    assert back["is_multichannel"] is True
    assert back["gainmap_min"] == (
        pytest.approx(-0.5),
        pytest.approx(-0.25),
        pytest.approx(0.0),
    )


def test_encode_single_channel_unchanged():
    back = _parse_iso21496_metadata(
        _encode_iso21496_metadata({"gainmap_min": (0.5,), "gainmap_max": (2.0,)})
    )
    assert back["is_multichannel"] is False
    assert back["gainmap_min"] == (pytest.approx(0.5),)


def test_encode_flagged_multichannel_expands_single_values():
    back = _parse_iso21496_metadata(
        _encode_iso21496_metadata(
            {"is_multichannel": True, "gainmap_min": (0.5,), "gainmap_max": (2.0,)}
        )
    )
    assert back["is_multichannel"] is True
    assert back["gainmap_max"] == (2.0, 2.0, 2.0)


# -----------------------------------------------------------------------------
# Bit depth alignment (confirmed #6)
# -----------------------------------------------------------------------------


def test_align_uint16_shifts_dark_10bit_data():
    # 10-bit content scaled to 16-bit by pillow_heif: native 13 -> 832.
    arr = np.full((2, 2, 3), 832, dtype=np.uint16)
    assert int(_align_uint16_to_bit_depth(arr, 10)[0, 0, 0]) == 13


def test_align_uint16_passthrough_for_none_and_16():
    arr = np.full((2, 2, 3), 832, dtype=np.uint16)
    assert _align_uint16_to_bit_depth(arr, None) is arr
    assert _align_uint16_to_bit_depth(arr, 16) is arr


# -----------------------------------------------------------------------------
# Zero-denominator rationals (confirmed #4)
# -----------------------------------------------------------------------------


def test_read_rational_zero_denominator_raises():
    with pytest.raises(ValueError, match="zero denominator"):
        _read_rational(struct.pack(">II", 1, 0), 0)


def test_zero_denominator_gamma_fails_parse():
    body = bytearray(_metadata_body())
    # gamma rational of channel 0 sits at offset 5 + 16 + 16.
    body[37:45] = struct.pack(">II", 1, 0)
    with pytest.raises(ValueError):
        _parse_iso21496_metadata(ISO21496_URN + bytes(body))


# -----------------------------------------------------------------------------
# ffprobe/ffmpeg failures raise RuntimeError with diagnostics (confirmed #7)
# -----------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_probe_video_item_failure_raises_runtimeerror(tmp_path):
    garbage = tmp_path / "garbage.bin"
    garbage.write_bytes(b"not a video at all")
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _probe_video_item(str(garbage))


# -----------------------------------------------------------------------------
# ISOBMFF candidate errors surface in the final error (confirmed #5)
# -----------------------------------------------------------------------------


def test_isobmff_read_reports_candidate_errors(monkeypatch):
    monkeypatch.setattr(iso21496, "_check_mp4box_installed", lambda: None)
    monkeypatch.setattr(iso21496, "_check_ffmpeg_installed", lambda: None)
    monkeypatch.setattr(
        iso21496, "_parse_isobmff_structure", lambda filepath, temp_dir: {}
    )
    monkeypatch.setattr(
        iso21496, "_select_isobmff_tmap_items", lambda structure: [(3, 1, 2)]
    )

    def boom(filepath, item_id, temp_dir):
        raise RuntimeError("ffmpeg exploded: no codec")

    monkeypatch.setattr(iso21496, "_dump_isobmff_item_bytes", boom)

    with pytest.raises(RuntimeError, match="tmap item 3: ffmpeg exploded: no codec"):
        iso21496._read_21496_isobmff("dummy.avif")


# -----------------------------------------------------------------------------
# Incomplete ICC chunks (plausible #0)
# -----------------------------------------------------------------------------


def test_extract_icc_incomplete_chunks_warns_and_returns_none():
    seg1 = b"ICC_PROFILE\x00" + bytes([1, 3]) + b"chunk1"
    seg3 = b"ICC_PROFILE\x00" + bytes([3, 3]) + b"chunk3"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _extract_icc([(APP2, seg1), (APP2, seg3)])
    assert result is None
    assert any("Incomplete ICC profile" in str(w.message) for w in caught)


def test_extract_icc_complete_chunks_assemble():
    seg1 = b"ICC_PROFILE\x00" + bytes([1, 2]) + b"chunk1"
    seg2 = b"ICC_PROFILE\x00" + bytes([2, 2]) + b"chunk2"
    assert _extract_icc([(APP2, seg1), (APP2, seg2)]) == b"chunk1chunk2"


# -----------------------------------------------------------------------------
# Dead code removal (confirmed #2/#30)
# -----------------------------------------------------------------------------


def test_dead_mpf_offset_helper_removed():
    assert not hasattr(iso21496, "_find_mpf_gainmap_offset")
