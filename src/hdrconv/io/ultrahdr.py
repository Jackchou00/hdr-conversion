"""UltraHDR (JPEG Gainmap) I/O operations.

This module provides functions for reading and writing UltraHDR-like JPEG
files that store a gainmap as a secondary JPEG stream in an MPF container,
with Adobe HDR Gain Map metadata embedded as XMP (APP1).

Public APIs:
    - `read_ultrahdr`: Read UltraHDR JPEG to GainmapImage
    - `write_ultrahdr`: Write GainmapImage to UltraHDR JPEG

Note:
    This is a minimal, MPF-based implementation. It does not require
    GContainer metadata in the primary image; it only depends on MPF to locate
    the gainmap stream and XMP in the gainmap stream for metadata.
"""

from __future__ import annotations

import io
import warnings
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from hdrconv.core import GainmapImage, GainmapMetadata
from hdrconv.io._jpeg import (
    APP2,
    assemble_mpf_file,
    build_icc_segments,
    build_mpf_minimal_payload,
    build_segment,
    encode_jpeg,
    insert_segments,
    normalize_to_uint8,
)
from hdrconv.io.iso21496 import (
    _extract_icc,
    _split_mpf_container,
    _yield_jpeg_segments,
)

SOI = b"\xff\xd8"
APP1 = 0xFFE1
XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
HDRGM_NS = "http://ns.adobe.com/hdr-gain-map/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

# Fields that carry actual gain-map data. hdrgm:Version alone (always present
# in the primary stream's GContainer XMP) does not qualify as metadata.
_HDRGM_DATA_FIELDS = (
    "GainMapMin",
    "GainMapMax",
    "Gamma",
    "OffsetSDR",
    "OffsetHDR",
    "HDRCapacityMin",
    "HDRCapacityMax",
)


# -----------------------------------------------------------------------------
# XMP Parsing / Encoding
# -----------------------------------------------------------------------------


def _extract_xmp_payload(app1_payload: bytes) -> Optional[str]:
    if app1_payload.startswith(XMP_HEADER):
        xml_bytes = app1_payload[len(XMP_HEADER) :]
    else:
        # Try to locate XML start
        start = app1_payload.find(b"<")
        if start == -1:
            return None
        xml_bytes = app1_payload[start:]

    try:
        return xml_bytes.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return None


def _parse_hdrgm_value(value: str) -> Any:
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_hdrgm_metadata(xmp_xml: str) -> Dict[str, Any]:
    try:
        root = ET.fromstring(xmp_xml)
    except ET.ParseError:
        return {}

    namespaces = {"rdf": RDF_NS, "hdrgm": HDRGM_NS}
    # The root may be x:xmpmeta wrapping rdf:RDF, or a bare rdf:RDF.
    if root.tag == "{" + RDF_NS + "}RDF":
        descriptions = root.findall("rdf:Description", namespaces)
    else:
        descriptions = root.findall("rdf:RDF/rdf:Description", namespaces)

    metadata: Dict[str, Any] = {}

    # Merge hdrgm attributes/children across all rdf:Description blocks
    for description in descriptions:
        # Attributes
        for key, value in description.attrib.items():
            if key.startswith("{" + HDRGM_NS + "}"):
                clean_key = key.replace("{" + HDRGM_NS + "}", "")
                metadata[clean_key] = _parse_hdrgm_value(value)

        # Child elements: rdf:Seq lists or element-form simple properties
        for child in list(description):
            if not child.tag.startswith("{" + HDRGM_NS + "}"):
                continue
            clean_key = child.tag.replace("{" + HDRGM_NS + "}", "")
            seq = child.find("rdf:Seq", namespaces)
            if seq is None:
                if child.text and child.text.strip():
                    metadata[clean_key] = _parse_hdrgm_value(child.text)
                continue
            values: List[float] = []
            for li in seq.findall("rdf:li", namespaces):
                if li.text:
                    try:
                        values.append(float(li.text.strip()))
                    except ValueError:
                        continue
            if values:
                metadata[clean_key] = values

    return metadata


def _channel_values(value: Any, default: float = 0.0) -> Tuple[float, ...]:
    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return (float(value[0]),)
        if len(value) == 3:
            return (float(value[0]), float(value[1]), float(value[2]))
        return (float(default),)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return (float(value),)
    return (float(default),)


def _hdrgm_to_gainmap_metadata(
    hdrgm: Dict[str, Any], gainmap: np.ndarray
) -> GainmapMetadata:
    gainmap_min = _channel_values(hdrgm.get("GainMapMin", 0.0), 0.0)
    gainmap_max = _channel_values(hdrgm.get("GainMapMax", 1.0), 1.0)
    gainmap_gamma = _channel_values(hdrgm.get("Gamma", 1.0), 1.0)
    # Adobe Gain Map 1.0 default for OffsetSDR/OffsetHDR is 1/64
    baseline_offset = _channel_values(hdrgm.get("OffsetSDR", 0.015625), 0.015625)
    alternate_offset = _channel_values(hdrgm.get("OffsetHDR", 0.015625), 0.015625)

    # Adobe spec defaults: HDRCapacityMin is 0.0; use max(GainMapMax) as a
    # fallback for HDRCapacityMax if absent.
    capacity_min = hdrgm.get("HDRCapacityMin", None)
    capacity_max = hdrgm.get("HDRCapacityMax", None)
    if capacity_min is None:
        capacity_min = 0.0
    if capacity_max is None:
        capacity_max = float(np.max(gainmap_max))

    baseline_hdr_headroom = float(capacity_min)
    alternate_hdr_headroom = float(capacity_max)

    is_multichannel = False
    if gainmap.ndim == 3 and gainmap.shape[2] >= 3:
        # Treat as multichannel if metadata values differ per channel
        def is_triple_distinct(values: Tuple[float, ...]) -> bool:
            if len(values) != 3:
                return False
            return not (
                abs(values[0] - values[1]) < 1e-6 and abs(values[0] - values[2]) < 1e-6
            )

        is_multichannel = any(
            is_triple_distinct(v)
            for v in [
                gainmap_min,
                gainmap_max,
                gainmap_gamma,
                baseline_offset,
                alternate_offset,
            ]
        )

        if not is_multichannel:
            # Metadata triples can be uniform while the decoded gainmap still
            # carries distinct per-channel data. Compare channels on a cheap
            # subsample; tolerate a few codes of JPEG chroma round-trip noise.
            sample = gainmap[::16, ::16].astype(np.int16)
            channel_span = np.abs(sample[..., :3] - sample[..., :1]).max()
            is_multichannel = bool(channel_span > 2)

    return GainmapMetadata(
        minimum_version=0,
        writer_version=0,
        baseline_hdr_headroom=baseline_hdr_headroom,
        alternate_hdr_headroom=alternate_hdr_headroom,
        is_multichannel=is_multichannel,
        use_base_colour_space=True,
        gainmap_min=gainmap_min,
        gainmap_max=gainmap_max,
        gainmap_gamma=gainmap_gamma,
        baseline_offset=baseline_offset,
        alternate_offset=alternate_offset,
    )


def _format_float(value: float) -> str:
    if abs(value) < 1e-6:
        return "0"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _to_triplet(values: Any, field_name: str) -> Tuple[float, float, float]:
    if isinstance(values, (int, float, np.integer, np.floating)):
        return (float(values), float(values), float(values))
    seq = tuple(float(v) for v in values)
    if len(seq) == 1:
        return (seq[0], seq[0], seq[0])
    if len(seq) == 3:
        return (seq[0], seq[1], seq[2])
    raise ValueError(
        f"Invalid metadata field '{field_name}': expected 1 or 3 values, got {len(seq)}."
    )


def _xmp_seq(tag: str, values: Tuple[float, float, float]) -> str:
    items = "".join(f"<rdf:li>{_format_float(v)}</rdf:li>" for v in values)
    return f"<hdrgm:{tag}><rdf:Seq>{items}</rdf:Seq></hdrgm:{tag}>"


def _build_hdrgm_xmp(metadata: GainmapMetadata) -> bytes:
    gainmap_min = _to_triplet(metadata.get("gainmap_min", (0.0,)), "gainmap_min")
    gainmap_max = _to_triplet(metadata.get("gainmap_max", (1.0,)), "gainmap_max")
    gainmap_gamma = _to_triplet(metadata.get("gainmap_gamma", (1.0,)), "gainmap_gamma")
    baseline_offset = _to_triplet(
        metadata.get("baseline_offset", (0.0,)), "baseline_offset"
    )
    alternate_offset = _to_triplet(
        metadata.get("alternate_offset", (0.0,)), "alternate_offset"
    )

    baseline_headroom = metadata.get("baseline_hdr_headroom", 0.0)
    alternate_headroom = metadata.get("alternate_hdr_headroom", 1.0)

    capacity_min = float(max(baseline_headroom, 1e-12))
    capacity_max = float(max(alternate_headroom, 1e-12))

    attrs = {
        "Version": "1.0",
        "GainMapMin": None,
        "GainMapMax": None,
        "Gamma": None,
        "OffsetSDR": None,
        "OffsetHDR": None,
        "HDRCapacityMin": _format_float(capacity_min),
        "HDRCapacityMax": _format_float(capacity_max),
        "BaseRenditionIsHDR": "False",
    }

    def maybe_scalar(values: Tuple[float, float, float]) -> Optional[str]:
        if abs(values[0] - values[1]) < 1e-6 and abs(values[0] - values[2]) < 1e-6:
            return _format_float(values[0])
        return None

    attrs["GainMapMin"] = maybe_scalar(gainmap_min)
    attrs["GainMapMax"] = maybe_scalar(gainmap_max)
    attrs["Gamma"] = maybe_scalar(gainmap_gamma)
    attrs["OffsetSDR"] = maybe_scalar(baseline_offset)
    attrs["OffsetHDR"] = maybe_scalar(alternate_offset)

    attr_str = " ".join(f'hdrgm:{k}="{v}"' for k, v in attrs.items() if v is not None)

    children = []
    if attrs["GainMapMin"] is None:
        children.append(_xmp_seq("GainMapMin", gainmap_min))
    if attrs["GainMapMax"] is None:
        children.append(_xmp_seq("GainMapMax", gainmap_max))
    if attrs["Gamma"] is None:
        children.append(_xmp_seq("Gamma", gainmap_gamma))
    if attrs["OffsetSDR"] is None:
        children.append(_xmp_seq("OffsetSDR", baseline_offset))
    if attrs["OffsetHDR"] is None:
        children.append(_xmp_seq("OffsetHDR", alternate_offset))

    children_xml = "".join(children)

    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        f'<rdf:Description xmlns:hdrgm="{HDRGM_NS}" {attr_str}>'
        f"{children_xml}"
        "</rdf:Description>"
        "</rdf:RDF>"
        "</x:xmpmeta>"
    )

    return XMP_HEADER + xmp.encode("utf-8")


def _build_gcontainer_xmp(gainmap_length: int) -> bytes:
    xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        "<rdf:Description "
        'xmlns:Container="http://ns.google.com/photos/1.0/container/" '
        'xmlns:Item="http://ns.google.com/photos/1.0/container/item/" '
        f'xmlns:hdrgm="{HDRGM_NS}" '
        'hdrgm:Version="1.0">'
        "<Container:Directory>"
        "<rdf:Seq>"
        '<rdf:li rdf:parseType="Resource">'
        '<Container:Item Item:Semantic="Primary" Item:Mime="image/jpeg"/>'
        "</rdf:li>"
        '<rdf:li rdf:parseType="Resource">'
        f'<Container:Item Item:Semantic="GainMap" Item:Mime="image/jpeg" Item:Length="{gainmap_length}"/>'
        "</rdf:li>"
        "</rdf:Seq>"
        "</Container:Directory>"
        "</rdf:Description>"
        "</rdf:RDF>"
        "</x:xmpmeta>"
    )
    return XMP_HEADER + xmp.encode("utf-8")


# -----------------------------------------------------------------------------
# Helper: JPEG stream splitting
# -----------------------------------------------------------------------------


def _find_jpeg_eoi(data: bytes) -> int:
    """Return the offset just past the first JPEG stream's EOI marker.

    Walks marker segments up to SOS, then scans entropy-coded data skipping
    stuffed 0xFF00 bytes and RSTn markers, so an FFD9FFD8 byte sequence
    inside a marker payload (EXIF, ICC, ...) cannot be mistaken for the end
    of the stream. Returns -1 if no EOI is found.
    """
    if data[:2] != SOI:
        return -1

    pos = 2
    length = len(data)
    in_scan = False

    while pos + 1 < length:
        if data[pos] != 0xFF:
            if not in_scan:
                return -1  # malformed marker structure
            nxt = data.find(b"\xff", pos)
            if nxt == -1:
                return -1
            pos = nxt
            continue

        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte before a marker
            pos += 1
            continue
        if marker == 0x00:  # stuffed data byte in entropy-coded data
            pos += 2
            continue
        if 0xD0 <= marker <= 0xD7:  # RSTn
            pos += 2
            continue
        if marker == 0xD9:  # EOI
            return pos + 2
        if marker in (0x01, 0xD8):  # TEM / SOI: standalone
            pos += 2
            continue

        # Marker segment with a length field (also ends the current scan
        # for progressive JPEGs).
        in_scan = False
        if pos + 4 > length:
            return -1
        seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
        if seg_len < 2:
            return -1
        if marker == 0xDA:  # SOS: entropy-coded data follows the header
            in_scan = True
        pos += 2 + seg_len

    return -1


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def read_ultrahdr(filepath: str) -> GainmapImage:
    """Read UltraHDR JPEG file.

    Args:
        filepath: Path to the UltraHDR JPEG file.

    Returns:
        GainmapImage dict containing baseline, gainmap, metadata, and ICC data.

    Raises:
        ValueError: If gainmap stream or HDR gainmap metadata is missing.
    """
    with open(filepath, "rb") as f:
        raw_data = f.read()

    primary_data, gainmap_data = _split_mpf_container(raw_data)

    # Fallback: split at the primary stream's true EOI if MPF is missing
    if not gainmap_data:
        eoi_end = _find_jpeg_eoi(raw_data)
        if eoi_end != -1 and raw_data[eoi_end : eoi_end + 2] == SOI:
            primary_data = raw_data[:eoi_end]
            gainmap_data = raw_data[eoi_end:]

    if not gainmap_data:
        raise ValueError("No gainmap found in container (MPF missing or invalid).")

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Image appears to be a malformed MPO file",
            category=UserWarning,
        )
        base_img = Image.open(io.BytesIO(primary_data)).convert("RGB")
        gain_img = Image.open(io.BytesIO(gainmap_data))
        if gain_img.mode not in ("L", "RGB"):
            gain_img = gain_img.convert("RGB")

    base_arr = np.array(base_img)
    gain_arr = np.array(gain_img)
    if gain_arr.ndim == 2:
        gain_arr = gain_arr[:, :, np.newaxis]
    elif gain_arr.ndim == 3 and gain_arr.shape[2] == 4:
        gain_arr = gain_arr[:, :, :3]

    base_segments = list(_yield_jpeg_segments(primary_data))
    gain_segments = list(_yield_jpeg_segments(gainmap_data))

    base_icc = _extract_icc(base_segments)
    gain_icc = _extract_icc(gain_segments)

    hdrgm_meta = None

    # Prefer gainmap stream
    for segments in [gain_segments, base_segments]:
        for code, payload in segments:
            if code == APP1:
                xmp_xml = _extract_xmp_payload(payload)
                if not xmp_xml:
                    continue
                parsed = _parse_hdrgm_metadata(xmp_xml)
                if parsed and any(k in parsed for k in _HDRGM_DATA_FIELDS):
                    hdrgm_meta = parsed
                    break
        if hdrgm_meta:
            break

    if not hdrgm_meta:
        raise ValueError("UltraHDR gainmap metadata (XMP) not found.")

    metadata = _hdrgm_to_gainmap_metadata(hdrgm_meta, gain_arr)

    return GainmapImage(
        baseline=base_arr,
        gainmap=gain_arr,
        metadata=metadata,
        baseline_icc=base_icc,
        gainmap_icc=gain_icc,
        baseline_bit_depth=8,
        gainmap_bit_depth=8,
    )


def write_ultrahdr(
    data: GainmapImage,
    filepath: str,
    baseline_quality: int = 95,
    gainmap_quality: int = 95,
) -> None:
    """Write UltraHDR JPEG file.

    Args:
        data: GainmapImage dict containing baseline, gainmap, and metadata.
        filepath: Output path for the JPEG file.
        baseline_quality: JPEG quality for baseline image (1-100, default 95).
        gainmap_quality: JPEG quality for gainmap image (1-100, default 95).
    """
    try:
        # Gainmap stream: minimal MPF, HDR gain map XMP, then ICC chunks.
        # Integer inputs deeper than 8 bits (e.g. from the ISOBMFF/screenshot
        # readers) are rescaled to uint8 using the recorded bit depth.
        gainmap_stream = insert_segments(
            encode_jpeg(
                normalize_to_uint8(data["gainmap"], data.get("gainmap_bit_depth")),
                gainmap_quality,
            ),
            [
                build_segment(APP2, build_mpf_minimal_payload(2)),
                build_segment(APP1, _build_hdrgm_xmp(data["metadata"])),
                *build_icc_segments(data.get("gainmap_icc")),
            ],
        )

        # Primary stream: GContainer XMP, MPF index to the gainmap, ICC.
        gcontainer_segment = build_segment(
            APP1, _build_gcontainer_xmp(len(gainmap_stream))
        )
        file_bytes = assemble_mpf_file(
            primary_jpeg=encode_jpeg(
                normalize_to_uint8(data["baseline"], data.get("baseline_bit_depth")),
                baseline_quality,
            ),
            gainmap_stream=gainmap_stream,
            segments_before_mpf=[gcontainer_segment],
            segments_after_mpf=build_icc_segments(data.get("baseline_icc")),
        )

        with open(filepath, "wb") as f:
            f.write(file_bytes)

    except Exception as e:
        raise RuntimeError(f"Failed to write UltraHDR file: {filepath}") from e
