import struct

import numpy as np
import pytest
from PIL import ImageCms

from hdrconv.icc.transfer import linearize_array_with_icc

SAMPLE = np.array([0.0, 0.02, 0.5, 1.0], dtype=np.float32)


def _srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _make_icc(tags) -> bytes:
    """Build a minimal ICC blob: 128-byte header, tag table, tag payloads."""
    header = bytes(128)
    tag_table = struct.pack(">I", len(tags))
    offset = 132 + 12 * len(tags)
    entries = b""
    body = b""
    for sig, payload in tags:
        entries += sig + struct.pack(">II", offset, len(payload))
        body += payload
        offset += len(payload)
    return header + tag_table + entries + body


def _curv_table_payload(values_u16) -> bytes:
    return (
        b"curv"
        + bytes(4)
        + struct.pack(">I", len(values_u16))
        + struct.pack(f">{len(values_u16)}H", *values_u16)
    )


def test_linearize_srgb_profile():
    linear = linearize_array_with_icc(_srgb_profile_bytes(), SAMPLE)
    # IEC 61966-2-1 sRGB EOTF reference values.
    expected = np.where(
        SAMPLE <= 0.04045, SAMPLE / 12.92, ((SAMPLE + 0.055) / 1.055) ** 2.4
    )
    np.testing.assert_allclose(linear, expected, atol=1e-4)


def test_gtrc_fallback_when_rtrc_missing():
    profile = _srgb_profile_bytes()
    expected = linearize_array_with_icc(profile, SAMPLE)

    # Rename the rTRC tag-table entry so only gTRC/bTRC remain.
    assert profile.count(b"rTRC") == 1
    mutated = profile.replace(b"rTRC", b"xTRC")

    linear = linearize_array_with_icc(mutated, SAMPLE)
    np.testing.assert_allclose(linear, expected)


def test_btrc_fallback_when_rtrc_and_gtrc_missing():
    profile = _srgb_profile_bytes()
    expected = linearize_array_with_icc(profile, SAMPLE)

    mutated = profile.replace(b"rTRC", b"xTRC").replace(b"gTRC", b"yTRC")

    linear = linearize_array_with_icc(mutated, SAMPLE)
    np.testing.assert_allclose(linear, expected)


def test_all_trc_missing_reports_missing_tags():
    mutated = (
        _srgb_profile_bytes()
        .replace(b"rTRC", b"xTRC")
        .replace(b"gTRC", b"yTRC")
        .replace(b"bTRC", b"zTRC")
    )
    with pytest.raises(ValueError, match="rTRC: tag missing"):
        linearize_array_with_icc(mutated, SAMPLE)


def test_unsupported_trc_type_distinguished_from_missing():
    # rTRC present but of an unhandled tag type ('text'); gTRC/bTRC absent.
    icc = _make_icc([(b"rTRC", b"text" + bytes(4))])
    with pytest.raises(ValueError) as excinfo:
        linearize_array_with_icc(icc, SAMPLE)
    message = str(excinfo.value)
    assert "rTRC: unsupported TRC type" in message
    assert "gTRC: tag missing" in message


def test_curv_table_interpolation_returns_float32():
    # Gamma-2 lookup table stored as a 'curv' tag.
    n = 256
    table = np.round((np.linspace(0.0, 1.0, n) ** 2) * 65535).astype(int)
    icc = _make_icc([(b"rTRC", _curv_table_payload(list(table)))])

    linear = linearize_array_with_icc(icc, SAMPLE)

    assert linear.dtype == np.float32
    np.testing.assert_allclose(linear, SAMPLE**2, atol=1e-3)
