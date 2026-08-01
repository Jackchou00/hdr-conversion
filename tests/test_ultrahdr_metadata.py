"""Tests for UltraHDR XMP metadata parsing and MPF-less stream splitting."""

from pathlib import Path

import numpy as np
import pytest

from hdrconv.core import GainmapMetadata
from hdrconv.io._jpeg import APP1, build_segment, encode_jpeg, insert_segments
from hdrconv.io.ultrahdr import (
    _build_gcontainer_xmp,
    _build_hdrgm_xmp,
    _find_jpeg_eoi,
    _hdrgm_to_gainmap_metadata,
    _parse_hdrgm_metadata,
    read_ultrahdr,
)

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

HDRGM_NS_DECL = 'xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"'
RDF_NS_DECL = 'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'


def _sample_metadata() -> GainmapMetadata:
    return GainmapMetadata(
        minimum_version=0,
        writer_version=0,
        baseline_hdr_headroom=0.0,
        alternate_hdr_headroom=2.0,
        is_multichannel=False,
        use_base_colour_space=True,
        gainmap_min=(0.0,),
        gainmap_max=(2.0,),
        gainmap_gamma=(1.0,),
        baseline_offset=(0.015625,),
        alternate_offset=(0.015625,),
    )


def _base_and_gain_arrays():
    rng = np.random.default_rng(0)
    base = (rng.random((32, 48, 3)) * 255).astype(np.uint8)
    gain = (rng.random((16, 24, 1)) * 255).astype(np.uint8)
    return base, gain


def _poison_app1_segment() -> bytes:
    # APP1 payload that legally contains an EOI+SOI byte sequence.
    return build_segment(
        APP1, b"Exif\x00\x00" + b"\x01" * 10 + b"\xff\xd9\xff\xd8" + b"\x02" * 10
    )


# -----------------------------------------------------------------------------
# _hdrgm_to_gainmap_metadata defaults (Adobe Gain Map 1.0)
# -----------------------------------------------------------------------------


def test_offset_defaults_are_one_sixty_fourth():
    gainmap = np.zeros((4, 4, 1), np.uint8)
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMax": 2.3, "HDRCapacityMax": 2.3}, gainmap
    )
    assert meta["baseline_offset"] == (0.015625,)
    assert meta["alternate_offset"] == (0.015625,)


def test_explicit_offsets_are_kept():
    gainmap = np.zeros((4, 4, 1), np.uint8)
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMax": 2.3, "OffsetSDR": 0.0, "OffsetHDR": 0.0},
        gainmap,
    )
    assert meta["baseline_offset"] == (0.0,)
    assert meta["alternate_offset"] == (0.0,)


def test_capacity_min_defaults_to_zero_not_gainmap_min():
    gainmap = np.zeros((4, 4, 1), np.uint8)
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMin": -0.5, "GainMapMax": 2.3, "HDRCapacityMax": 2.3},
        gainmap,
    )
    assert meta["baseline_hdr_headroom"] == 0.0


# -----------------------------------------------------------------------------
# is_multichannel detection from decoded gainmap data
# -----------------------------------------------------------------------------


def test_multichannel_detected_from_pixel_data_with_uniform_metadata():
    gainmap = np.zeros((64, 64, 3), np.uint8)
    gainmap[..., 0] = 200
    gainmap[..., 1] = 100
    gainmap[..., 2] = 50
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMax": 2.3, "HDRCapacityMax": 2.3}, gainmap
    )
    assert meta["is_multichannel"] is True


def test_multichannel_not_triggered_by_chroma_noise():
    # A gray gainmap stored as RGB JPEG decodes with ~1-code channel noise.
    gainmap = np.full((64, 64, 3), 100, np.uint8)
    gainmap[..., 1] = 101
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMax": 2.3, "HDRCapacityMax": 2.3}, gainmap
    )
    assert meta["is_multichannel"] is False


def test_multichannel_detected_from_metadata_triples():
    gainmap = np.zeros((64, 64, 3), np.uint8)
    meta = _hdrgm_to_gainmap_metadata(
        {"Version": 1.0, "GainMapMax": [1.0, 2.0, 3.0], "HDRCapacityMax": 3.0},
        gainmap,
    )
    assert meta["is_multichannel"] is True


# -----------------------------------------------------------------------------
# _parse_hdrgm_metadata XMP serialization variants
# -----------------------------------------------------------------------------


def test_parse_attribute_form():
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        f"<rdf:RDF {RDF_NS_DECL}>"
        f'<rdf:Description {HDRGM_NS_DECL} hdrgm:Version="1.0" '
        'hdrgm:GainMapMax="2.3" hdrgm:Gamma="1.2"/>'
        "</rdf:RDF></x:xmpmeta>"
    )
    parsed = _parse_hdrgm_metadata(xmp)
    assert parsed == {"Version": 1.0, "GainMapMax": 2.3, "Gamma": 1.2}


def test_parse_element_form_simple_properties():
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        f"<rdf:RDF {RDF_NS_DECL}>"
        f"<rdf:Description {HDRGM_NS_DECL}>"
        "<hdrgm:Version>1.0</hdrgm:Version>"
        "<hdrgm:GainMapMax>2.3</hdrgm:GainMapMax>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
    )
    parsed = _parse_hdrgm_metadata(xmp)
    assert parsed == {"Version": 1.0, "GainMapMax": 2.3}


def test_parse_multiple_descriptions_merged():
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        f"<rdf:RDF {RDF_NS_DECL}>"
        f'<rdf:Description {HDRGM_NS_DECL} hdrgm:Version="1.0"/>'
        f'<rdf:Description {HDRGM_NS_DECL} hdrgm:GainMapMax="2.3" hdrgm:Gamma="1.2"/>'
        "</rdf:RDF></x:xmpmeta>"
    )
    parsed = _parse_hdrgm_metadata(xmp)
    assert parsed == {"Version": 1.0, "GainMapMax": 2.3, "Gamma": 1.2}


def test_parse_bare_rdf_root():
    xmp = (
        f"<rdf:RDF {RDF_NS_DECL}>"
        f'<rdf:Description {HDRGM_NS_DECL} hdrgm:GainMapMax="2.3"/>'
        "</rdf:RDF>"
    )
    parsed = _parse_hdrgm_metadata(xmp)
    assert parsed == {"GainMapMax": 2.3}


def test_parse_seq_form_still_works():
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        f"<rdf:RDF {RDF_NS_DECL}>"
        f"<rdf:Description {HDRGM_NS_DECL}>"
        "<hdrgm:GainMapMax><rdf:Seq>"
        "<rdf:li>1.0</rdf:li><rdf:li>2.0</rdf:li><rdf:li>3.0</rdf:li>"
        "</rdf:Seq></hdrgm:GainMapMax>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
    )
    parsed = _parse_hdrgm_metadata(xmp)
    assert parsed == {"GainMapMax": [1.0, 2.0, 3.0]}


# -----------------------------------------------------------------------------
# MPF-less fallback split
# -----------------------------------------------------------------------------


def test_find_jpeg_eoi_skips_marker_payloads_and_entropy_data():
    base, _ = _base_and_gain_arrays()
    jpeg = insert_segments(encode_jpeg(base), [_poison_app1_segment()])
    assert _find_jpeg_eoi(jpeg) == len(jpeg)


def test_sdr_jpeg_with_poisoned_app1_raises_value_error(tmp_path):
    base, _ = _base_and_gain_arrays()
    jpeg = insert_segments(encode_jpeg(base), [_poison_app1_segment()])
    path = tmp_path / "sdr_poison.jpg"
    path.write_bytes(jpeg)
    with pytest.raises(ValueError, match="No gainmap found"):
        read_ultrahdr(str(path))


def test_mpfless_concatenation_with_poisoned_app1_splits_correctly(tmp_path):
    base, gain = _base_and_gain_arrays()
    gain_stream = insert_segments(
        encode_jpeg(gain),
        [build_segment(APP1, _build_hdrgm_xmp(_sample_metadata()))],
    )
    primary = insert_segments(encode_jpeg(base), [_poison_app1_segment()])
    path = tmp_path / "mpfless.jpg"
    path.write_bytes(primary + gain_stream)

    result = read_ultrahdr(str(path))
    assert result["baseline"].shape == (32, 48, 3)
    assert result["gainmap"].shape == (16, 24, 1)
    assert result["metadata"]["gainmap_max"] == (2.0,)


# -----------------------------------------------------------------------------
# XMP acceptance: Version-only metadata must not be fabricated into defaults
# -----------------------------------------------------------------------------


def test_version_only_xmp_raises_value_error(tmp_path):
    base, gain = _base_and_gain_arrays()
    gain_stream = encode_jpeg(gain)  # no XMP in the gainmap stream
    primary = insert_segments(
        encode_jpeg(base),
        [build_segment(APP1, _build_gcontainer_xmp(len(gain_stream)))],
    )
    path = tmp_path / "version_only.jpg"
    path.write_bytes(primary + gain_stream)
    with pytest.raises(ValueError, match="metadata \\(XMP\\) not found"):
        read_ultrahdr(str(path))


# -----------------------------------------------------------------------------
# Sample-file regression
# -----------------------------------------------------------------------------


@pytest.mark.skipif(
    not (IMAGES_DIR / "uhdr.jpg").exists(), reason="sample image not available"
)
def test_read_uhdr_sample_metadata():
    result = read_ultrahdr(str(IMAGES_DIR / "uhdr.jpg"))
    meta = result["metadata"]
    assert meta["baseline_hdr_headroom"] == 0.0
    assert meta["alternate_hdr_headroom"] == pytest.approx(2.281494)
    assert meta["is_multichannel"] is True
    assert meta["gainmap_min"] == pytest.approx((-2.149567, -2.139404, -2.134003))
    assert meta["gainmap_max"] == pytest.approx((2.234985, 2.213623, 2.147125))
    assert meta["baseline_offset"] == (0.015625,)
    assert meta["alternate_offset"] == (0.015625,)


@pytest.mark.skipif(
    not (IMAGES_DIR / "uhdr_x6p.jpg").exists(), reason="sample image not available"
)
def test_read_uhdr_x6p_sample_metadata():
    result = read_ultrahdr(str(IMAGES_DIR / "uhdr_x6p.jpg"))
    meta = result["metadata"]
    assert meta["baseline_hdr_headroom"] == 0.0
    assert meta["alternate_hdr_headroom"] == pytest.approx(1.55652)
    assert meta["is_multichannel"] is False
    assert meta["gainmap_max"] == pytest.approx((1.55652,))
    # Explicit zeros in the file must not be replaced by the 1/64 default.
    assert meta["baseline_offset"] == (0.0,)
    assert meta["alternate_offset"] == (0.0,)
