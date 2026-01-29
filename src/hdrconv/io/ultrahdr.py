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
from hdrconv.io.iso21496 import (
    _build_app2_segment,
    _build_mpf_minimal_payload,
    _build_mpf_payload,
    _create_jpeg_bytes,
    _extract_icc,
    _split_mpf_container,
    _yield_jpeg_segments,
)

SOI = b"\xff\xd8"
APP1 = 0xFFE1
XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
HDRGM_NS = "http://ns.adobe.com/hdr-gain-map/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


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
    description = root.find("rdf:RDF/rdf:Description", namespaces)
    if description is None:
        return {}

    metadata: Dict[str, Any] = {}

    # Attributes
    for key, value in description.attrib.items():
        if key.startswith("{" + HDRGM_NS + "}"):
            clean_key = key.replace("{" + HDRGM_NS + "}", "")
            metadata[clean_key] = _parse_hdrgm_value(value)

    # Child elements with rdf:Seq
    for child in list(description):
        if not child.tag.startswith("{" + HDRGM_NS + "}"):
            continue
        clean_key = child.tag.replace("{" + HDRGM_NS + "}", "")
        seq = child.find("rdf:Seq", namespaces)
        if seq is None:
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


def _triple(value: Any, default: float = 0.0) -> Tuple[float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if isinstance(value, (int, float)):
        return (float(value), float(value), float(value))
    return (float(default), float(default), float(default))


def _hdrgm_to_gainmap_metadata(
    hdrgm: Dict[str, Any], gainmap: np.ndarray
) -> GainmapMetadata:
    gainmap_min = _triple(hdrgm.get("GainMapMin", 0.0), 0.0)
    gainmap_max = _triple(hdrgm.get("GainMapMax", 1.0), 1.0)
    gainmap_gamma = _triple(hdrgm.get("Gamma", 1.0), 1.0)
    baseline_offset = _triple(hdrgm.get("OffsetSDR", 0.0), 0.0)
    alternate_offset = _triple(hdrgm.get("OffsetHDR", 0.0), 0.0)

    # Use gainmap min/max for HDR capacity if explicit values are absent
    capacity_min = hdrgm.get("HDRCapacityMin", None)
    capacity_max = hdrgm.get("HDRCapacityMax", None)
    if capacity_min is None:
        capacity_min = float(np.min(gainmap_min))
    if capacity_max is None:
        capacity_max = float(np.max(gainmap_max))

    baseline_hdr_headroom = float(np.exp2(capacity_min))
    alternate_hdr_headroom = float(np.exp2(capacity_max))

    is_multichannel = False
    if gainmap.ndim == 3 and gainmap.shape[2] >= 3:
        # Treat as multichannel only if values differ per channel
        def is_triple_distinct(values: Tuple[float, float, float]) -> bool:
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


def _xmp_seq(tag: str, values: Tuple[float, float, float]) -> str:
    items = "".join(f"<rdf:li>{_format_float(v)}</rdf:li>" for v in values)
    return f"<hdrgm:{tag}><rdf:Seq>{items}</rdf:Seq></hdrgm:{tag}>"


def _build_hdrgm_xmp(metadata: GainmapMetadata) -> bytes:
    gainmap_min = metadata.get("gainmap_min", (0.0, 0.0, 0.0))
    gainmap_max = metadata.get("gainmap_max", (1.0, 1.0, 1.0))
    gainmap_gamma = metadata.get("gainmap_gamma", (1.0, 1.0, 1.0))
    baseline_offset = metadata.get("baseline_offset", (0.0, 0.0, 0.0))
    alternate_offset = metadata.get("alternate_offset", (0.0, 0.0, 0.0))

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


def _build_app1_segment(payload: bytes) -> bytes:
    length = len(payload) + 2
    return b"\xff\xe1" + length.to_bytes(2, "big") + payload


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

    # Fallback: split by EOI+SOI if MPF is missing
    if not gainmap_data:
        separator = b"\xff\xd9\xff\xd8"
        split_pos = raw_data.find(separator)
        if split_pos != -1:
            primary_data = raw_data[: split_pos + 2]
            gainmap_data = raw_data[split_pos + 2 :]

    if not gainmap_data:
        raise ValueError("No gainmap found in container (MPF missing or invalid).")

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Image appears to be a malformed MPO file",
            category=UserWarning,
        )
        base_img = Image.open(io.BytesIO(primary_data)).convert("RGB")
        gain_img = Image.open(io.BytesIO(gainmap_data)).convert("RGB")

    base_arr = np.array(base_img)
    gain_arr = np.array(gain_img)

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
                if parsed and ("GainMapMin" in parsed or "Version" in parsed):
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
    )


def write_ultrahdr(data: GainmapImage, filepath: str) -> None:
    """Write UltraHDR JPEG file.

    Args:
        data: GainmapImage dict containing baseline, gainmap, and metadata.
        filepath: Output path for the JPEG file.
    """
    try:
        gainmap_bytes_raw = _create_jpeg_bytes(data["gainmap"], data.get("gainmap_icc"))

        # Insert minimal MPF APP2 in gainmap stream for compatibility
        gainmap_mpf_segment = _build_app2_segment(_build_mpf_minimal_payload(2))

        xmp_payload = _build_hdrgm_xmp(data["metadata"])
        xmp_segment = _build_app1_segment(xmp_payload)

        gainmap_final = (
            gainmap_bytes_raw[:2]
            + gainmap_mpf_segment
            + xmp_segment
            + gainmap_bytes_raw[2:]
        )

        primary_bytes_raw = _create_jpeg_bytes(
            data["baseline"], data.get("baseline_icc")
        )

        gcontainer_payload = _build_gcontainer_xmp(len(gainmap_final))
        gcontainer_segment = _build_app1_segment(gcontainer_payload)

        mpf_payload_temp = _build_mpf_payload(
            primary_size=len(primary_bytes_raw),
            gainmap_size=len(gainmap_final),
            gainmap_offset=0,
        )
        mpf_segment_temp = _build_app2_segment(mpf_payload_temp)

        total_primary_len = (
            len(primary_bytes_raw) + len(gcontainer_segment) + len(mpf_segment_temp)
        )

        mpf_marker_offset = 2 + len(gcontainer_segment)
        mpf_base_file_offset = mpf_marker_offset + 8
        gainmap_relative_offset = total_primary_len - mpf_base_file_offset

        mpf_payload_final = _build_mpf_payload(
            primary_size=total_primary_len,
            gainmap_size=len(gainmap_final),
            gainmap_offset=gainmap_relative_offset,
        )
        mpf_segment_final = _build_app2_segment(mpf_payload_final)

        primary_final = (
            primary_bytes_raw[:2]
            + gcontainer_segment
            + mpf_segment_final
            + primary_bytes_raw[2:]
        )

        with open(filepath, "wb") as f:
            f.write(primary_final)
            f.write(gainmap_final)

    except Exception as e:
        raise RuntimeError(f"Failed to write UltraHDR file: {filepath}") from e
