"""ISO 21496-1 Gainmap JPEG I/O operations.

This module provides functions for reading and writing ISO 21496-1 compliant
gainmap JPEG files using Multi-Picture Format (MPF) container structure.

Public APIs:
    - `read_21496`: Read gainmap JPEG to GainmapImage
    - `write_21496`: Write GainmapImage to gainmap JPEG

The ISO 21496-1 format embeds a gainmap as a secondary image in an MPF
container, with metadata stored in APP2 segments using a specific URN.
"""

from __future__ import annotations
from hdrconv.core import GainmapImage


import io
import shutil
import struct
import subprocess
import tempfile
import warnings
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np
import pillow_heif
from PIL import Image

# -----------------------------------------------------------------------------
# Constants & Markers
# -----------------------------------------------------------------------------

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"
SOS = 0xFFDA
APP2 = 0xFFE2
ICC_PROFILE_LABEL = b"ICC_PROFILE\x00"
MPF_LABEL = b"MPF\x00"
# ISO 21496-1 Signature in APP2
ISO21496_URN = b"urn:iso:std:iso:ts:21496:-1\x00"
ISO21496_URN_ALT = b"urn:iso:std:iso:ts:21496:-1"  # Some writers omit null
JPEG_21496_EXTENSIONS = {".jpg", ".jpeg", ".jpe"}
ISOBMFF_21496_EXTENSIONS = {".heic", ".heif", ".hif", ".avif", ".avifs"}

# -----------------------------------------------------------------------------
# Helper: JPEG Segment Parsing
# -----------------------------------------------------------------------------


def _yield_jpeg_segments(data: bytes) -> Generator[Tuple[int, bytes], None, None]:
    """Yield JPEG segments from raw file data.

    Parses JPEG marker segments from the start of file up to the Start of Scan
    (SOS) marker, yielding each segment's marker code and payload.

    Args:
        data: Raw JPEG file bytes starting with SOI marker.

    Yields:
        Tuple of (marker_code, payload) where marker_code is the 16-bit
        marker (e.g., 0xFFE2 for APP2) and payload is the segment data
        excluding the marker and length bytes.

    Note:
        Stops scanning at SOS to avoid parsing compressed image data.
        Skips standalone markers (RSTn, TEM) that have no payload.
    """
    if data[:2] != SOI:
        return

    pos = 2
    length = len(data)

    while pos < length - 1:
        # Find next marker 0xFF
        if data[pos] != 0xFF:
            pos += 1
            continue

        marker = data[pos + 1]
        pos += 2

        # Skip padding 0xFF
        while marker == 0xFF and pos < length:
            marker = data[pos]
            pos += 1

        marker_code = 0xFF00 | marker

        # Standalone markers (no payload)
        if marker_code == SOS:
            yield marker_code, b""
            break  # Stop scanning at SOS to save time
        if marker_code == 0xFFD9:  # EOI
            break
        if 0xFFD0 <= marker_code <= 0xFFD7 or marker_code == 0xFF01:  # RSTn or TEM
            continue

        # Markers with payload
        if pos + 2 > length:
            break
        seg_len = int.from_bytes(data[pos : pos + 2], "big")
        # seg_len includes the 2 bytes for length itself
        payload_start = pos + 2
        payload_end = pos + seg_len

        if payload_end > length:
            break

        yield marker_code, data[payload_start:payload_end]
        pos = payload_end


# -----------------------------------------------------------------------------
# Helper: ICC & MPF Extraction
# -----------------------------------------------------------------------------


def _extract_icc(segments: List[Tuple[int, bytes]]) -> Optional[bytes]:
    """Extract and reassemble ICC profile from APP2 segments.

    ICC profiles may be split across multiple APP2 segments when larger
    than the maximum segment size. This function reassembles them.

    Args:
        segments: List of (marker_code, payload) tuples from JPEG parsing.

    Returns:
        Complete ICC profile bytes if found, None otherwise.

    Note:
        Handles chunked ICC profiles with sequence numbers.
        Validates chunk consistency but assembles available chunks
        even if some are missing.
    """
    chunks = {}
    expected_total = None

    for code, payload in segments:
        if code == APP2 and payload.startswith(ICC_PROFILE_LABEL):
            # Format: ID(12) + seq(1) + total(1) + data...
            if len(payload) < 14:
                continue
            seq = payload[12]
            total = payload[13]

            # Validate total consistency
            if expected_total is None:
                expected_total = total
            elif expected_total != total:
                # Inconsistent total values - file may be corrupted
                continue

            chunks[seq] = payload[14:]

    if not chunks:
        return None

    # Validate completeness (optional - warns but doesn't fail)
    if expected_total and len(chunks) != expected_total:
        # Missing chunks - assemble what we have but it may be incomplete
        pass

    # Assemble in order
    return b"".join(chunks[i] for i in sorted(chunks.keys()))


def _find_mpf_gainmap_offset(segments: List[Tuple[int, bytes]], file_len: int) -> int:
    """
    Parses MPF APP2 to find the offset of the second image (Gainmap).
    Returns 0 if not found.
    """
    for code, payload in segments:
        if code == APP2 and payload.startswith(MPF_LABEL):
            # Simplified MPF parser focusing on the Index IFD
            # Header: 'MPF\0' (4) + Endian(2) + 0x002A(2) + OffsetIFD(4)
            if len(payload) < 8:
                continue

            endian_sig = payload[4:6]
            endian = ">" if endian_sig == b"MM" else "<"

            try:
                first_ifd_offset = struct.unpack(f"{endian}I", payload[8:12])[0]
                # Jump to First IFD (Index IFD)
                # MPF Structure relative to the "MM/II" start (index 4 in payload)
                base = 4
                ifd_pos = base + first_ifd_offset
                num_entries = struct.unpack(
                    f"{endian}H", payload[ifd_pos : ifd_pos + 2]
                )[0]

                # Iterate MPF tags to find MP Entry tag (0xB002)
                entry_cursor = ifd_pos + 2
                mp_entries_data = None

                for _ in range(num_entries):
                    tag, typ, cnt, val_off = struct.unpack(
                        f"{endian}HHII", payload[entry_cursor : entry_cursor + 12]
                    )
                    if tag == 0xB002:  # MP Entry Tag
                        # Value is offset to the MP Entry list
                        data_off = base + val_off
                        # Each entry is 16 bytes
                        mp_entries_data = payload[data_off : data_off + (cnt * 16)]
                        break
                    entry_cursor += 12

                if mp_entries_data and len(mp_entries_data) >= 32:
                    # Look at second entry (Index 1) for the gainmap
                    # Entry structure: Attr(4), Size(4), Offset(4), Dep1(2), Dep2(2)
                    # Offset is relative to the MPF header start in the file.
                    # Usually, MPF header start = current_segment_offset + 4 + 4 (marker+len+MPF_sig...)
                    # Ideally, we calculate relative to file start if possible, but standard says relative to MPF header.

                    # Entry 2 starts at byte 16
                    e2_offset_val = struct.unpack(f"{endian}I", mp_entries_data[24:28])[
                        0
                    ]
                    if e2_offset_val > 0:
                        # We need the absolute file position.
                        # This implementation assumes standard construction where we can't easily get the absolute
                        # pos of the segment without tracking it.
                        # However, for decoding, we split the bytes.
                        # Note: This simple parser assumes the MPF logic implies encoded_iso21496 style structure.
                        # A robust one would track `pos` in the scanner.
                        pass

            except Exception:
                pass

    # Fallback: Many MPF implementations simply concatenate.
    # If we want to be precise, we need the segment offset.
    # Let's rely on a simpler heuristic for this utility:
    # The MPF offset is relative to the MPF Header (Start of 'MM'/'II').
    # We will return the extracted relative offset if found, but caller needs context.

    # RE-IMPLEMENTATION WITH OFFSET TRACKING
    # To correctly handle MPF, we need to scan the raw bytes again or return offsets from scanner.
    return 0


def _split_mpf_container(data: bytes) -> Tuple[bytes, bytes]:
    """Split MPF container into primary and secondary images.

    Parses the Multi-Picture Format (MPF) structure to locate and
    extract the primary baseline image and secondary gainmap image.

    Args:
        data: Complete JPEG file bytes containing MPF structure.

    Returns:
        Tuple of (primary_bytes, gainmap_bytes). If MPF parsing fails
        or no secondary image is found, gainmap_bytes will be empty.

    Note:
        Uses MPF Index IFD to locate the offset of the second image.
        Falls back to returning only primary if split fails.
    """
    if data[:2] != SOI:
        return data, b""

    # 1. Scan marker segments of the primary JPEG only (from SOI to SOS).
    # This avoids false APP2 hits inside entropy-coded scan data.
    pos = 2
    data_len = len(data)
    second_image_offset = 0

    while pos < data_len - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue

        marker_pos = pos
        marker_byte = data[pos + 1]
        pos += 2

        while marker_byte == 0xFF and pos < data_len:
            marker_byte = data[pos]
            pos += 1

        marker_code = 0xFF00 | marker_byte

        # Stop at SOS: markers after this point are inside compressed stream.
        if marker_code == SOS:
            break
        if marker_code == 0xFFD9:  # EOI
            break
        if 0xFFD0 <= marker_code <= 0xFFD7 or marker_code == 0xFF01:
            continue

        if pos + 2 > data_len:
            break
        seg_len = int.from_bytes(data[pos : pos + 2], "big")
        payload_start = pos + 2
        payload_end = pos + seg_len
        if seg_len < 2 or payload_end > data_len:
            break
        payload = data[payload_start:payload_end]

        if marker_code == APP2 and payload.startswith(MPF_LABEL):
            # MPF header base is at the TIFF header ("MM"/"II"), i.e. after MPF\0.
            mpf_offset_base = marker_pos + 8
            try:
                if len(payload) < 12:
                    break

                endian_sig = payload[4:6]
                if endian_sig == b"MM":
                    endian = ">"
                elif endian_sig == b"II":
                    endian = "<"
                else:
                    break

                base = 4
                first_ifd = struct.unpack(f"{endian}I", payload[8:12])[0]
                ifd_idx = base + first_ifd
                if ifd_idx + 2 > len(payload):
                    break

                entry_count = struct.unpack(
                    f"{endian}H", payload[ifd_idx : ifd_idx + 2]
                )[0]
                cursor = ifd_idx + 2
                entries_offset_local = 0

                for _ in range(entry_count):
                    if cursor + 12 > len(payload):
                        break
                    tag, _, _, val = struct.unpack(
                        f"{endian}HHII", payload[cursor : cursor + 12]
                    )
                    if tag == 0xB002:
                        entries_offset_local = val
                        break
                    cursor += 12

                if entries_offset_local:
                    # Read 2nd MP Entry (index 1): Attr(4), Size(4), Offset(4), Dep(4)
                    entry2_pos = base + entries_offset_local + 16
                    if entry2_pos + 12 <= len(payload):
                        img2_offset = struct.unpack(
                            f"{endian}I", payload[entry2_pos + 8 : entry2_pos + 12]
                        )[0]
                        if img2_offset > 0:
                            second_image_offset = mpf_offset_base + img2_offset
            except Exception:
                pass
            break

        pos = payload_end

    if second_image_offset > 0 and second_image_offset < data_len:
        return data[:second_image_offset], data[second_image_offset:]

    # Fallback: Return only primary if split fails
    return data, b""


# -----------------------------------------------------------------------------
# ISO 21496-1 Logic
# -----------------------------------------------------------------------------


def _read_rational(data: bytes, offset: int, signed: bool = False) -> float:
    fmt = ">iI" if signed else ">II"
    num, den = struct.unpack_from(fmt, data, offset)
    return num / den if den != 0 else 0.0


def _has_iso21496_urn(payload: bytes) -> bool:
    return payload.startswith(ISO21496_URN) or payload.startswith(ISO21496_URN_ALT)


def _strip_iso21496_urn(payload: bytes) -> tuple[bytes, bool]:
    if payload.startswith(ISO21496_URN):
        return payload[len(ISO21496_URN) :], True
    if payload.startswith(ISO21496_URN_ALT):
        return payload[len(ISO21496_URN_ALT) :], True
    return payload, False


def _expected_iso21496_binary_length(payload: bytes) -> int:
    if len(payload) < 5:
        raise ValueError(
            f"ISO 21496-1 metadata too short: expected at least 5 bytes, got {len(payload)}."
        )
    flags = payload[4]
    channel_count = 3 if ((flags >> 7) & 1) else 1
    return 5 + 16 + (channel_count * 40)


def _iter_iso21496_binary_candidates(payload: bytes) -> Generator[bytes, None, None]:
    body, had_urn = _strip_iso21496_urn(payload)
    yield body

    # HEIF/AVIF tmap payloads may include a leading one-byte version marker
    # before the standard ISO 21496-1 metadata block. JPEG APP2 payloads do not.
    if not had_urn and len(body) > 1:
        yield body[1:]


def _parse_iso21496_binary_payload(payload: bytes) -> Dict[str, Any]:
    """Parse the standard ISO 21496-1 binary metadata block."""

    expected_length = _expected_iso21496_binary_length(payload)
    if len(payload) != expected_length:
        raise ValueError(
            "Invalid ISO 21496-1 metadata length: "
            f"expected {expected_length} bytes, got {len(payload)}."
        )

    offset = 0

    # Header
    min_ver, writer_ver, flags = struct.unpack_from(">HHB", payload, offset)
    offset += 5

    is_multichannel = bool((flags >> 7) & 1)
    use_base_space = bool((flags >> 6) & 1)

    # Headroom
    base_headroom = _read_rational(payload, offset, False)
    offset += 8
    alt_headroom = _read_rational(payload, offset, False)
    offset += 8

    # Channels
    channel_count = 3 if is_multichannel else 1
    channels = []

    for _ in range(channel_count):
        c = {}
        c["min"] = _read_rational(payload, offset, True)
        offset += 8
        c["max"] = _read_rational(payload, offset, True)
        offset += 8
        c["gamma"] = _read_rational(payload, offset, False)
        offset += 8
        c["base_off"] = _read_rational(payload, offset, True)
        offset += 8
        c["alt_off"] = _read_rational(payload, offset, True)
        offset += 8
        channels.append(c)

    # Format to Output Structure
    # TODO: Keep source channel cardinality (1 or 3) in parsed metadata.
    # Expansion should happen at use sites (conversion/writing), not read time.
    def get_channel_values(key: str) -> Tuple[float, ...]:
        if is_multichannel:
            return (channels[0][key], channels[1][key], channels[2][key])
        else:
            v = channels[0][key]
            return (v,)

    return {
        "alternate_hdr_headroom": float(alt_headroom),
        "baseline_hdr_headroom": float(base_headroom),
        "is_multichannel": is_multichannel,
        "use_base_colour_space": use_base_space,
        "minimum_version": min_ver,  # Should be 0
        "writer_version": writer_ver,
        "alternate_offset": get_channel_values("alt_off"),
        "baseline_offset": get_channel_values("base_off"),
        "gainmap_min": get_channel_values("min"),
        "gainmap_max": get_channel_values("max"),
        "gainmap_gamma": get_channel_values("gamma"),
    }


def _coerce_channel_values(
    values: Any, field_name: str, default: Tuple[float, ...]
) -> Tuple[float, ...]:
    if values is None:
        seq = default
    elif isinstance(values, (int, float, np.integer, np.floating)):
        seq = (float(values),)
    else:
        seq = tuple(float(v) for v in values)

    if len(seq) not in (1, 3):
        raise ValueError(
            f"Invalid {field_name}: expected 1 or 3 values, got {len(seq)}."
        )
    return seq


def _to_triplet(values: Tuple[float, ...]) -> Tuple[float, float, float]:
    if len(values) == 3:
        return (values[0], values[1], values[2])
    return (values[0], values[0], values[0])


def _parse_iso21496_metadata(payload: bytes) -> Dict[str, Any]:
    """Parse ISO 21496-1 metadata from JPEG APP2 or raw HEIF/AVIF tmap bytes."""

    last_error: Exception | None = None
    for candidate in _iter_iso21496_binary_candidates(payload):
        try:
            return _parse_iso21496_binary_payload(candidate)
        except (ValueError, struct.error) as e:
            last_error = e

    raise ValueError("Invalid ISO 21496-1 metadata payload.") from last_error


def _find_iso21496_metadata(
    segment_groups: List[List[Tuple[int, bytes]]],
) -> Optional[Dict[str, Any]]:
    for segments in segment_groups:
        for code, payload in segments:
            if code != APP2 or not _has_iso21496_urn(payload):
                continue
            try:
                return _parse_iso21496_metadata(payload)
            except ValueError:
                continue
    return None


def _check_mp4box_installed() -> None:
    if shutil.which("MP4Box") is None:
        raise RuntimeError(
            "MP4Box is not installed or not found in PATH. "
            "Please install GPAC and ensure MP4Box is available."
        )


def _run_mp4box(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"MP4Box command failed: {' '.join(args)}\n{detail}")
    return result


def _dump_isobmff_item_bytes(filepath: str, item_id: int, temp_dir: str) -> bytes:
    output_path = Path(temp_dir) / f"item_{item_id}.bin"
    param = f"{item_id}:path={output_path}"
    _run_mp4box(["MP4Box", "-dump-item", param, filepath])

    if not output_path.exists():
        raise RuntimeError(f"MP4Box did not dump item {item_id} from {filepath}.")

    return output_path.read_bytes()


def _check_ffmpeg_installed() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Missing required external tools: {', '.join(missing)}. "
            "Please install FFmpeg and ensure ffmpeg/ffprobe are available."
        )


def _local_xml_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_isobmff_structure(filepath: str, temp_dir: str) -> dict[str, Any]:
    xml_path = Path(temp_dir) / "isobmff_info.xml"
    _run_mp4box(["MP4Box", "-diso", filepath, "-out", str(xml_path)])

    root = ET.parse(xml_path).getroot()
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0][1:]
    ns = {"m": namespace} if namespace else {}
    prefix = ".//m:" if namespace else ".//"
    child_prefix = "./m:" if namespace else "./"

    primary_box = root.find(f"{prefix}PrimaryItemBox", ns)
    primary_id = int(primary_box.attrib["item_ID"]) if primary_box is not None else None

    items: dict[int, dict[str, Any]] = {}
    for entry in root.findall(f"{prefix}ItemInfoEntryBox", ns):
        item_id = int(entry.attrib["item_ID"])
        flags = int(entry.attrib.get("Flags", "0"))
        items[item_id] = {
            "type": entry.attrib.get("item_type"),
            "flags": flags,
            "hidden": bool(flags & 1),
            "content_type": entry.attrib.get("content_type"),
            "name": entry.attrib.get("item_name"),
        }

    refs: dict[tuple[str, int], list[int]] = {}
    for ref in root.findall(f"{prefix}ItemReferenceBox", ns):
        ref_type = ref.attrib.get("Type")
        from_item_id = ref.attrib.get("from_item_id")
        if not from_item_id or ref_type == "iref":
            continue
        refs[(ref_type, int(from_item_id))] = [
            int(entry.attrib["ItemID"])
            for entry in ref.findall(f"{child_prefix}ItemReferenceBoxEntry", ns)
        ]

    groups: list[tuple[str, int, list[int]]] = []
    for group in root.findall(f"{prefix}EntityToGroupTypeBox", ns):
        groups.append(
            (
                group.attrib.get("Type", ""),
                int(group.attrib.get("group_id", "0")),
                [
                    int(entry.attrib["EntityID"])
                    for entry in group.findall(
                        f"{child_prefix}EntityToGroupTypeBoxEntry", ns
                    )
                ],
            )
        )

    properties: list[tuple[str, dict[str, str], list[int]]] = []
    property_container = root.find(f"{prefix}ItemPropertyContainerBox", ns)
    if property_container is not None:
        for child in property_container:
            bits = [
                int(bit.attrib["bits_per_channel"])
                for bit in child.findall(f"{child_prefix}BitPerChannel", ns)
            ]
            properties.append((_local_xml_tag(child.tag), child.attrib, bits))

    associations: dict[int, list[int]] = {}
    for entry in root.findall(f"{prefix}AssociationEntry", ns):
        item_id = int(entry.attrib["item_ID"])
        associations[item_id] = [
            int(prop.attrib["index"])
            for prop in entry.findall(f"{child_prefix}Property", ns)
        ]

    return {
        "primary_id": primary_id,
        "items": items,
        "refs": refs,
        "groups": groups,
        "properties": properties,
        "associations": associations,
    }


def _get_isobmff_item_property(
    structure: dict[str, Any], item_id: int, property_type: str
) -> Optional[tuple[dict[str, str], list[int]]]:
    properties = structure["properties"]
    for property_index in structure["associations"].get(item_id, []):
        if not 1 <= property_index <= len(properties):
            continue
        tag, attrs, bits = properties[property_index - 1]
        if tag == property_type:
            return attrs, bits
    return None


def _get_isobmff_item_bit_depth(
    structure: dict[str, Any], item_id: int
) -> Optional[int]:
    prop = _get_isobmff_item_property(structure, item_id, "PixelInformationPropertyBox")
    if prop is None:
        return None
    _, bits = prop
    return max(bits) if bits else None


def _require_isobmff_item_bit_depth(
    structure: dict[str, Any], item_id: int, field_name: str
) -> int:
    bit_depth = _get_isobmff_item_bit_depth(structure, item_id)
    if bit_depth is None:
        raise ValueError(
            f"Missing bit depth for {field_name} item {item_id} in ISOBMFF properties."
        )
    return bit_depth


def _get_isobmff_item_channel_count(structure: dict[str, Any], item_id: int) -> int:
    prop = _get_isobmff_item_property(structure, item_id, "PixelInformationPropertyBox")
    if prop is None:
        return 3
    _, bits = prop
    if len(bits) in (1, 3, 4):
        return len(bits)
    return 3


def _select_isobmff_tmap_items(
    structure: dict[str, Any],
) -> list[tuple[int, int, int]]:
    selected = []
    items = structure["items"]
    refs = structure["refs"]
    altr_groups = [
        entities
        for group_type, _, entities in structure["groups"]
        if group_type == "altr"
    ]

    for tmap_id, info in items.items():
        if info.get("type") != "tmap":
            continue
        derived_items = refs.get(("dimg", tmap_id), [])
        if len(derived_items) < 2:
            continue
        baseline_id, gainmap_id = derived_items[:2]

        # altr should contain tmap and baseline. Treat it as validation when present.
        if altr_groups and not any(
            tmap_id in group and baseline_id in group for group in altr_groups
        ):
            continue

        selected.append((tmap_id, baseline_id, gainmap_id))

    return selected


def _align_uint16_to_bit_depth(arr: np.ndarray, bit_depth: Optional[int]) -> np.ndarray:
    if bit_depth is None or bit_depth >= 16:
        return arr

    max_value = (1 << bit_depth) - 1
    if arr.size == 0 or int(arr.max()) <= max_value:
        return arr

    shift = 16 - bit_depth
    return (arr >> shift).astype(np.uint16, copy=False)


def _heif_image_to_array(image: Any, bit_depth: Optional[int] = None) -> np.ndarray:
    width, height = image.size
    mode = image.mode

    if mode == "RGB":
        row_bytes = width * 3
        return (
            np.frombuffer(image.data, dtype=np.uint8)
            .reshape(height, image.stride)[:, :row_bytes]
            .reshape(height, width, 3)
            .copy()
        )
    if mode == "L":
        return (
            np.frombuffer(image.data, dtype=np.uint8)
            .reshape(height, image.stride)[:, :width]
            .reshape(height, width, 1)
            .copy()
        )
    if mode == "RGBA":
        row_bytes = width * 4
        return (
            np.frombuffer(image.data, dtype=np.uint8)
            .reshape(height, image.stride)[:, :row_bytes]
            .reshape(height, width, 4)[:, :, :3]
            .copy()
        )
    if mode == "RGB;16":
        row_samples = width * 3
        arr = (
            np.frombuffer(image.data, dtype=np.uint16)
            .reshape(height, image.stride // 2)[:, :row_samples]
            .reshape(height, width, 3)
            .copy()
        )
        return _align_uint16_to_bit_depth(arr, bit_depth)
    if mode == "L;16":
        arr = (
            np.frombuffer(image.data, dtype=np.uint16)
            .reshape(height, image.stride // 2)[:, :width]
            .reshape(height, width, 1)
            .copy()
        )
        return _align_uint16_to_bit_depth(arr, bit_depth)

    raise ValueError(f"Unsupported HEIF image mode: {mode}")


def _read_isobmff_primary_image(
    filepath: str, bit_depth: Optional[int]
) -> tuple[np.ndarray, Optional[bytes], int]:
    heif_file = pillow_heif.read_heif(filepath, convert_hdr_to_8bit=False)
    actual_bit_depth = bit_depth
    if actual_bit_depth is None:
        decoder_bit_depth = heif_file.info.get("bit_depth")
        if decoder_bit_depth is not None:
            actual_bit_depth = int(decoder_bit_depth)
    if actual_bit_depth is None:
        raise ValueError(f"Missing decoder bit depth for primary image: {filepath}")

    return (
        _heif_image_to_array(heif_file, actual_bit_depth),
        heif_file.info.get("icc_profile"),
        actual_bit_depth,
    )


def _try_read_isobmff_aux_image(
    filepath: str, item_id: int, bit_depth: int
) -> Optional[np.ndarray]:
    heif_file = pillow_heif.read_heif(filepath, convert_hdr_to_8bit=False)
    aux_items = heif_file.info.get("aux", {})
    if not any(item_id in ids for ids in aux_items.values()):
        return None

    aux_image = heif_file.get_aux_image(item_id)
    return _heif_image_to_array(aux_image, bit_depth)


def _probe_video_item(path: str) -> tuple[int, int, str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,pix_fmt",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height, pix_fmt = result.stdout.strip().split(",")
    return int(width), int(height), pix_fmt


def _select_rawvideo_pix_fmt(channel_count: int, bit_depth: int) -> str:
    if channel_count == 1:
        if bit_depth <= 8:
            return "gray"
        return f"gray{bit_depth}le"
    if bit_depth <= 8:
        return "rgb24"
    return f"gbrp{bit_depth}le"


def _decode_video_item_to_array(
    path: str,
    channel_count: int,
    bit_depth: int,
) -> np.ndarray:
    width, height, _ = _probe_video_item(path)
    pix_fmt = _select_rawvideo_pix_fmt(channel_count, bit_depth)
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            path,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            pix_fmt,
            "-",
        ],
        capture_output=True,
        check=True,
    )

    if pix_fmt == "gray":
        return (
            np.frombuffer(result.stdout, dtype=np.uint8)
            .reshape(height, width, 1)
            .copy()
        )
    if pix_fmt.startswith("gray") and pix_fmt.endswith("le"):
        return (
            np.frombuffer(result.stdout, dtype=np.uint16)
            .reshape(height, width, 1)
            .copy()
        )
    if pix_fmt == "rgb24":
        return (
            np.frombuffer(result.stdout, dtype=np.uint8)
            .reshape(height, width, 3)
            .copy()
        )
    if pix_fmt.startswith("gbrp") and pix_fmt.endswith("le"):
        planes = np.frombuffer(result.stdout, dtype=np.uint16).reshape(3, height, width)
        return np.stack([planes[2], planes[0], planes[1]], axis=-1).copy()

    raise ValueError(f"Unsupported rawvideo pixel format: {pix_fmt}")


def _parse_grid_item_payload(data: bytes) -> tuple[int, int, int, int]:
    if len(data) != 8:
        raise ValueError(f"Unsupported grid item payload length: {len(data)}")

    rows = data[2] + 1
    cols = data[3] + 1
    width = int.from_bytes(data[4:6], "big")
    height = int.from_bytes(data[6:8], "big")
    return rows, cols, width, height


def _read_isobmff_grid_image(
    filepath: str,
    item_id: int,
    structure: dict[str, Any],
    temp_dir: str,
) -> np.ndarray:
    tile_ids = structure["refs"].get(("dimg", item_id), [])
    if not tile_ids:
        raise ValueError(f"Grid image item {item_id} has no dimg tile references.")

    grid_data = _dump_isobmff_item_bytes(filepath, item_id, temp_dir)
    rows, cols, output_width, output_height = _parse_grid_item_payload(grid_data)
    if rows * cols != len(tile_ids):
        raise ValueError(
            f"Grid item {item_id} expects {rows * cols} tiles, got {len(tile_ids)}."
        )

    channel_count = _get_isobmff_item_channel_count(structure, item_id)
    bit_depth = _require_isobmff_item_bit_depth(structure, item_id, "grid")
    tile_arrays = []

    for tile_id in tile_ids:
        tile_path = Path(temp_dir) / f"tile_{tile_id}.bitstream"
        param = f"{tile_id}:path={tile_path}"
        _run_mp4box(["MP4Box", "-dump-item", param, filepath])
        tile_arrays.append(
            _decode_video_item_to_array(str(tile_path), channel_count, bit_depth)
        )

    tile_height, tile_width = tile_arrays[0].shape[:2]
    channels = tile_arrays[0].shape[2]
    canvas = np.zeros(
        (rows * tile_height, cols * tile_width, channels),
        dtype=tile_arrays[0].dtype,
    )

    for index, tile in enumerate(tile_arrays):
        row = index // cols
        col = index % cols
        y = row * tile_height
        x = col * tile_width
        canvas[y : y + tile_height, x : x + tile_width] = tile

    return canvas[:output_height, :output_width].copy()


def _read_isobmff_item_image(
    filepath: str,
    item_id: int,
    structure: dict[str, Any],
    temp_dir: str,
) -> np.ndarray:
    item = structure["items"].get(item_id)
    if item is None:
        raise ValueError(f"Image item {item_id} not found.")

    item_type = item.get("type")
    if item_type == "grid":
        return _read_isobmff_grid_image(filepath, item_id, structure, temp_dir)

    item_path = Path(temp_dir) / f"image_item_{item_id}.bitstream"
    param = f"{item_id}:path={item_path}"
    _run_mp4box(["MP4Box", "-dump-item", param, filepath])
    channel_count = _get_isobmff_item_channel_count(structure, item_id)
    bit_depth = _require_isobmff_item_bit_depth(structure, item_id, "image")
    return _decode_video_item_to_array(str(item_path), channel_count, bit_depth)


def _encode_iso21496_metadata(meta: Dict[str, Any]) -> bytes:
    """Encodes the metadata dict into binary APP2 payload."""

    def to_rational(val: float, signed: bool) -> Tuple[int, int]:
        f = Fraction(val).limit_denominator(100000)
        num, den = f.numerator, f.denominator
        if signed:
            num = max(-(2**31), min(2**31 - 1, num))
            den = max(1, min(2**32 - 1, den))
        else:
            num = max(0, min(2**32 - 1, num))
            den = max(1, min(2**32 - 1, den))
        return int(num), int(den)

    out = bytearray()
    out.extend(ISO21496_URN)

    min_ver = meta.get("minimum_version", 0)
    wri_ver = meta.get("writer_version", 0)
    is_mc = meta.get("is_multichannel", False)
    use_base = meta.get("use_base_colour_space", False)

    flags = (1 if is_mc else 0) << 7 | (1 if use_base else 0) << 6
    out.extend(struct.pack(">HHB", min_ver, wri_ver, flags))

    # Headroom
    n, d = to_rational(meta.get("baseline_hdr_headroom", 0.0), False)
    out.extend(struct.pack(">II", n, d))
    n, d = to_rational(meta.get("alternate_hdr_headroom", 0.0), False)
    out.extend(struct.pack(">II", n, d))

    # Channels
    gm_min = _coerce_channel_values(meta.get("gainmap_min"), "gainmap_min", (0.0,))
    gm_max = _coerce_channel_values(meta.get("gainmap_max"), "gainmap_max", (1.0,))
    gm_gam = _coerce_channel_values(meta.get("gainmap_gamma"), "gainmap_gamma", (1.0,))
    base_off = _coerce_channel_values(
        meta.get("baseline_offset"), "baseline_offset", (0.0,)
    )
    alt_off = _coerce_channel_values(
        meta.get("alternate_offset"), "alternate_offset", (0.0,)
    )

    if is_mc:
        count = 3
        gm_min_w = _to_triplet(gm_min)
        gm_max_w = _to_triplet(gm_max)
        gm_gam_w = _to_triplet(gm_gam)
        base_off_w = _to_triplet(base_off)
        alt_off_w = _to_triplet(alt_off)
    else:
        count = 1
        gm_min_w = (gm_min[0],)
        gm_max_w = (gm_max[0],)
        gm_gam_w = (gm_gam[0],)
        base_off_w = (base_off[0],)
        alt_off_w = (alt_off[0],)

    for i in range(count):
        # min (signed)
        n, d = to_rational(gm_min_w[i], True)
        out.extend(struct.pack(">iI", n, d))
        # max (signed)
        n, d = to_rational(gm_max_w[i], True)
        out.extend(struct.pack(">iI", n, d))
        # gamma (unsigned)
        n, d = to_rational(gm_gam_w[i], False)
        out.extend(struct.pack(">II", n, d))
        # base offset (signed)
        n, d = to_rational(base_off_w[i], True)
        out.extend(struct.pack(">iI", n, d))
        # alt offset (signed)
        n, d = to_rational(alt_off_w[i], True)
        out.extend(struct.pack(">iI", n, d))

    return bytes(out)


# -----------------------------------------------------------------------------
# Encoding Helpers
# -----------------------------------------------------------------------------


def _create_jpeg_bytes(
    img_arr: np.ndarray, icc: bytes | None, quality: int = 95
) -> bytes:
    """Encode numpy array to JPEG bytes using PIL."""
    # Convert to uint8 if needed
    if img_arr.dtype != np.uint8:
        if np.issubdtype(img_arr.dtype, np.floating):
            img_arr = np.clip(img_arr * 255, 0, 255).astype(np.uint8)
        else:
            img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)

    # Ensure PIL-compatible format (L or RGB)
    if img_arr.ndim == 2:
        pass
    elif img_arr.shape[2] == 1:
        img_arr = img_arr[:, :, 0]
    elif img_arr.shape[2] == 4:
        img_arr = img_arr[:, :, :3]  # Drop alpha channel

    pil_img = Image.fromarray(img_arr)
    bio = io.BytesIO()

    save_kwargs = {
        "format": "JPEG",
        "quality": quality,
        "subsampling": 0,  # 4:4:4 chroma subsampling for best quality
    }
    if icc:
        save_kwargs["icc_profile"] = icc

    pil_img.save(bio, **save_kwargs)
    return bio.getvalue()


def _build_app2_segment(payload: bytes) -> bytes:
    """Build JPEG APP2 segment with given payload."""
    # Marker (FF E2) + Length (2 bytes) + Payload
    length = len(payload) + 2
    return b"\xff\xe2" + length.to_bytes(2, "big") + payload


def _build_mpf_payload(
    primary_size: int, gainmap_size: int, gainmap_offset: int
) -> bytes:
    """Build MPF (Multi-Picture Format) binary payload with 2 image entries."""
    # MPF signature
    mpf_sig = b"MPF\x00"
    # Big endian byte order
    byte_order = b"MM"

    # Build MP Entry List (16 bytes per entry: Attribute, Size, Offset, Dependent)
    entries = bytearray()

    # Entry 0: Primary Image (CIPA DC-007 standard attribute 0x00030000)
    entries.extend(struct.pack(">I", 0x00030000))
    entries.extend(struct.pack(">I", primary_size))
    entries.extend(struct.pack(">I", 0))  # Offset 0 (self)
    entries.extend(struct.pack(">I", 0))  # No dependent entries

    # Entry 1: Gainmap Image (CIPA DC-007 standard attribute 0x00050000)
    entries.extend(struct.pack(">I", 0x00050000))
    entries.extend(struct.pack(">I", gainmap_size))
    entries.extend(struct.pack(">I", gainmap_offset))
    entries.extend(struct.pack(">I", 0))

    # Build Index IFD with 3 tags: Version, NumberOfImages, MPEntry
    num_tags = 3
    ifd = bytearray()

    # Tag 1: MPF Version (0xB000)
    ifd.extend(struct.pack(">H", 0xB000))
    ifd.extend(struct.pack(">H", 7))  # Type: UNDEFINED
    ifd.extend(struct.pack(">I", 4))  # Count: 4
    ifd.extend(b"0100")  # Value: "0100"

    # Tag 2: Number of Images (0xB001)
    ifd.extend(struct.pack(">H", 0xB001))
    ifd.extend(struct.pack(">H", 4))  # Type: LONG
    ifd.extend(struct.pack(">I", 1))  # Count: 1
    ifd.extend(struct.pack(">I", 2))  # Value: 2 images

    # Tag 3: MP Entry (0xB002)
    ifd.extend(struct.pack(">H", 0xB002))
    ifd.extend(struct.pack(">H", 7))  # Type: UNDEFINED
    ifd.extend(struct.pack(">I", 32))  # Count: 32 bytes (2 entries * 16)
    # Offset to data: Header(8) + Count(2) + Tags(36) + NextIFD(4) = 50 bytes
    ifd.extend(struct.pack(">I", 50))

    # Assemble all parts
    payload = bytearray()
    payload.extend(mpf_sig)
    payload.extend(byte_order)
    payload.extend(b"\x00\x2a")  # TIFF magic number
    payload.extend(struct.pack(">I", 8))  # Offset to first IFD

    # IFD block
    payload.extend(struct.pack(">H", num_tags))
    payload.extend(ifd)
    payload.extend(struct.pack(">I", 0))  # No next IFD

    # Data area (entries)
    payload.extend(entries)

    return bytes(payload)


def _build_mpf_minimal_payload(num_images: int) -> bytes:
    """Build minimal MPF payload with Version and NumberOfImages only.

    Some implementations expect a minimal MPF APP2 in the gainmap stream.
    """
    mpf_sig = b"MPF\x00"
    byte_order = b"MM"

    num_tags = 2
    ifd = bytearray()

    # MPF Version (0xB000)
    ifd.extend(struct.pack(">H", 0xB000))
    ifd.extend(struct.pack(">H", 7))
    ifd.extend(struct.pack(">I", 4))
    ifd.extend(b"0100")

    # Number of Images (0xB001)
    ifd.extend(struct.pack(">H", 0xB001))
    ifd.extend(struct.pack(">H", 4))
    ifd.extend(struct.pack(">I", 1))
    ifd.extend(struct.pack(">I", int(num_images)))

    payload = bytearray()
    payload.extend(mpf_sig)
    payload.extend(byte_order)
    payload.extend(b"\x00\x2a")
    payload.extend(struct.pack(">I", 8))
    payload.extend(struct.pack(">H", num_tags))
    payload.extend(ifd)
    payload.extend(struct.pack(">I", 0))
    return bytes(payload)


def _calculate_mpf_offsets(
    primary_bytes_raw: bytes,
    primary_stub_segment: bytes,
    mpf_segment_temp: bytes,
) -> tuple[int, int, int]:
    """Calculate MPF-related file offsets.

    MPF standard specifies offsets relative to MPF Header (the 'MM'/'II' bytes).
    MPF Header is the first 8 bytes of MPF payload.

    File structure:
    - Primary JPEG raw data
    - Primary stub segment (APP2)
    - MPF segment (APP2)
    - Gainmap JPEG data

    Args:
        primary_bytes_raw: Raw JPEG bytes of primary image
        primary_stub_segment: Stub APP2 segment in primary
        mpf_segment_temp: MPF APP2 segment (for length calculation)

    Returns:
        tuple: (mpf_base_file_offset, gainmap_relative_offset, total_primary_len)
            - mpf_base_file_offset: MPF Header offset from file start
            - gainmap_relative_offset: Gainmap offset relative to MPF Header
            - total_primary_len: Total length of primary section
    """
    # Total length of primary section (including stub and MPF segments)
    total_primary_len = (
        len(primary_bytes_raw) + len(primary_stub_segment) + len(mpf_segment_temp)
    )

    # MPF marker offset (SOI marker 2 bytes + primary_stub_segment)
    mpf_marker_offset = 2 + len(primary_stub_segment)

    # MPF Header offset from file start
    # MPF marker (2 bytes) + segment length (2 bytes) + "MPF\0" (4 bytes) = 8 bytes
    mpf_base_file_offset = mpf_marker_offset + 8

    # Gainmap offset relative to MPF Header
    gainmap_relative_offset = total_primary_len - mpf_base_file_offset

    return mpf_base_file_offset, gainmap_relative_offset, total_primary_len


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def _read_21496_jpeg(filepath: str) -> GainmapImage:
    """Read ISO 21496-1 Gainmap JPEG file.

    Parses a JPEG file containing an ISO 21496-1 compliant gainmap with
    Multi-Picture Format (MPF) container structure.

    Args:
        filepath: Path to the ISO 21496-1 JPEG file.

    Returns:
        GainmapImage dict containing:
        - ``baseline`` (np.ndarray): SDR image, uint8, shape (H, W, 3), range [0, 255].
        - ``gainmap`` (np.ndarray): Gain map, uint8, shape (H, W, 3) or (H, W, 1).
        - ``metadata`` (GainmapMetadata): Transformation parameters including
            gamma, min/max values, offsets, and headroom.
        - ``baseline_icc`` (bytes | None): ICC profile for baseline image.
        - ``gainmap_icc`` (bytes | None): ICC profile for gainmap.

    Raises:
        ValueError: If gainmap is not found in MPF container.
        ValueError: If ISO 21496-1 metadata segment is missing.

    Note:
        The file must contain a valid MPF structure with the gainmap as
        the secondary image and ISO 21496-1 metadata in an APP2 segment.

    See Also:
        - `write_21496`: Write GainmapImage to ISO 21496-1 format.
        - `gainmap_to_hdr`: Convert GainmapImage to linear HDR.
    """
    with open(filepath, "rb") as f:
        raw_data = f.read()

    # 1. Split streams (Primary vs Gainmap) via MPF
    primary_data, gainmap_data = _split_mpf_container(raw_data)

    if not gainmap_data:
        raise ValueError("No gainmap found in container (MPF missing or invalid).")

    # 2. Decode Images
    # Suppress MPO-related warnings from Pillow when reading JPEG streams
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

    # 3. Extract Metadata & ICC
    # Metadata usually lives in the Gainmap stream's APP2, but we check both.

    base_segments = list(_yield_jpeg_segments(primary_data))
    gain_segments = list(_yield_jpeg_segments(gainmap_data))

    base_icc = _extract_icc(base_segments)
    gain_icc = _extract_icc(gain_segments)

    # Search for ISO 21496 metadata (Prioritize Gainmap stream)
    iso_meta = _find_iso21496_metadata([gain_segments, base_segments])

    if not iso_meta:
        raise ValueError("ISO 21496-1 metadata segment not found.")

    return GainmapImage(
        baseline=base_arr,
        gainmap=gain_arr,
        metadata=iso_meta,
        baseline_icc=base_icc,
        gainmap_icc=gain_icc,
        baseline_bit_depth=8,
        gainmap_bit_depth=8,
    )


def _read_21496_isobmff(filepath: str) -> GainmapImage:
    """Read ISO 21496-1 Gainmap HEIF/AVIF file."""
    _check_mp4box_installed()
    _check_ffmpeg_installed()

    last_error: Exception | None = None
    with tempfile.TemporaryDirectory(prefix="hdrconv_21496_") as temp_dir:
        structure = _parse_isobmff_structure(filepath, temp_dir)
        tmap_items = _select_isobmff_tmap_items(structure)
        if not tmap_items:
            raise ValueError(
                f"No tmap item with baseline/gainmap dimg references found: {filepath}"
            )

        for tmap_id, baseline_id, gainmap_id in tmap_items:
            try:
                tmap_data = _dump_isobmff_item_bytes(filepath, tmap_id, temp_dir)
                metadata = _parse_iso21496_metadata(tmap_data)
                baseline_bit_depth = _get_isobmff_item_bit_depth(structure, baseline_id)
                gainmap_bit_depth = _require_isobmff_item_bit_depth(
                    structure, gainmap_id, "gainmap"
                )

                if baseline_id == structure["primary_id"]:
                    (
                        baseline,
                        baseline_icc,
                        baseline_bit_depth,
                    ) = _read_isobmff_primary_image(filepath, baseline_bit_depth)
                else:
                    baseline_bit_depth = _require_isobmff_item_bit_depth(
                        structure, baseline_id, "baseline"
                    )
                    baseline = _read_isobmff_item_image(
                        filepath, baseline_id, structure, temp_dir
                    )
                    baseline_icc = None

                gainmap = _try_read_isobmff_aux_image(
                    filepath, gainmap_id, gainmap_bit_depth
                )
                if gainmap is None:
                    gainmap = _read_isobmff_item_image(
                        filepath, gainmap_id, structure, temp_dir
                    )

                return GainmapImage(
                    baseline=baseline,
                    gainmap=gainmap,
                    metadata=metadata,
                    baseline_icc=baseline_icc,
                    gainmap_icc=None,
                    baseline_bit_depth=baseline_bit_depth,
                    gainmap_bit_depth=gainmap_bit_depth,
                )
            except (RuntimeError, ValueError, struct.error) as e:
                last_error = e

    raise ValueError(
        f"No parseable ISO 21496-1 tmap metadata found in HEIF/AVIF container: {filepath}"
    ) from last_error


def _detect_21496_container(filepath: str) -> str:
    suffix = Path(filepath).suffix.lower()
    if suffix in JPEG_21496_EXTENSIONS:
        return "jpeg"
    if suffix in ISOBMFF_21496_EXTENSIONS:
        return "isobmff"

    with open(filepath, "rb") as f:
        header = f.read(12)

    if header.startswith(SOI):
        return "jpeg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "isobmff"

    raise ValueError(f"Unsupported ISO 21496-1 container format: {filepath}")


def read_21496(filepath: str) -> GainmapImage:
    """Read an ISO 21496-1 Gainmap image.

    Routes JPEG files to the MPF parser and HEIF/AVIF files to the ISOBMFF
    parser.
    """
    container = _detect_21496_container(filepath)
    if container == "jpeg":
        return _read_21496_jpeg(filepath)
    if container == "isobmff":
        return _read_21496_isobmff(filepath)

    raise ValueError(f"Unsupported ISO 21496-1 container format: {filepath}")


def write_21496(
    data: GainmapImage,
    filepath: str,
    baseline_quality: int = 95,
    gainmap_quality: int = 95,
) -> None:
    """Write ISO 21496-1 Gainmap JPEG file.

    Creates a JPEG file with ISO 21496-1 compliant gainmap structure using
    Multi-Picture Format (MPF) container.

    Args:
        data: GainmapImage dict containing:
            - ``baseline``: SDR image, uint8, shape (H, W, 3).
            - ``gainmap``: Gain map, uint8, shape (H, W, 3) or (H, W, 1).
            - ``metadata``: GainmapMetadata with transformation parameters.
            - ``baseline_icc``: Optional ICC profile for baseline.
            - ``gainmap_icc``: Optional ICC profile for gainmap.
        filepath: Output path for the JPEG file.
        baseline_quality: JPEG quality for baseline image (1-100, default 95).
        gainmap_quality: JPEG quality for gainmap image (1-100, default 95).

    Raises:
        RuntimeError: If file writing fails.

    Note:
        The output file structure places the baseline image first with an
        MPF index, followed by the gainmap with ISO 21496-1 metadata.
        JPEG quality is set to 95 with 4:4:4 chroma subsampling.

    See Also:
        - `read_21496`: Read ISO 21496-1 Gainmap JPEG.
        - `hdr_to_gainmap`: Convert HDR image to GainmapImage.
    """
    try:
        # Step 1: Encode gainmap image
        gainmap_bytes_raw = _create_jpeg_bytes(
            data["gainmap"], data.get("gainmap_icc"), gainmap_quality
        )

        # Step 1.1: Insert minimal MPF APP2 in gainmap stream for compatibility
        gainmap_mpf_segment = _build_app2_segment(_build_mpf_minimal_payload(2))

        # Step 2: Build ISO 21496-1 metadata segment (APP2)
        iso_payload = _encode_iso21496_metadata(data["metadata"])
        iso_segment = _build_app2_segment(iso_payload)

        # Insert ISO segment after SOI (0xFFD8) in gainmap
        gainmap_final = (
            gainmap_bytes_raw[:2]
            + gainmap_mpf_segment
            + iso_segment
            + gainmap_bytes_raw[2:]
        )

        # Step 3: Encode baseline image
        primary_bytes_raw = _create_jpeg_bytes(
            data["baseline"], data.get("baseline_icc"), baseline_quality
        )

        # Step 3.1: Insert URN stub APP2 in primary stream for compatibility
        primary_stub_segment = _build_app2_segment(ISO21496_URN + b"\x00\x00\x00\x00")

        # Step 4: Build MPF index segment (APP2)
        # MPF points to gainmap at end of file

        # Step 4.1: Generate MPF payload with placeholder offset for length calculation
        mpf_payload_temp = _build_mpf_payload(
            primary_size=len(primary_bytes_raw),
            gainmap_size=len(gainmap_final),
            gainmap_offset=0,  # Placeholder
        )
        mpf_segment_temp = _build_app2_segment(mpf_payload_temp)

        # Step 4.2: Calculate MPF-related file offsets
        _, gainmap_relative_offset, total_primary_len = _calculate_mpf_offsets(
            primary_bytes_raw,
            primary_stub_segment,
            mpf_segment_temp,
        )

        # Step 4.3: Regenerate MPF with correct primary size and gainmap offset
        mpf_payload_final = _build_mpf_payload(
            primary_size=total_primary_len,
            gainmap_size=len(gainmap_final),
            gainmap_offset=gainmap_relative_offset,
        )
        mpf_segment_final = _build_app2_segment(mpf_payload_final)

        # Step 5: Assemble baseline stream with MPF
        primary_final = (
            primary_bytes_raw[:2]
            + primary_stub_segment
            + mpf_segment_final
            + primary_bytes_raw[2:]
        )

        # Step 6: Write file (baseline + gainmap)
        with open(filepath, "wb") as f:
            f.write(primary_final)
            f.write(gainmap_final)

    except Exception as e:
        raise RuntimeError(f"Failed to write ISO 21496-1 file: {filepath}") from e
