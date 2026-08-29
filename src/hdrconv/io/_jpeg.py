"""Private JPEG segment and MPF container assembly helpers.

Shared by the ISO 21496-1 and UltraHDR writers. Provides baseline JPEG
encoding plus construction of APPn marker segments — including chunked
ICC profile embedding (ICC.1 Annex B) and the MPF (CIPA DC-007) index
needed to store a gainmap as a secondary image.

All multi-byte values are big-endian, matching JPEG and the "MM" TIFF
byte order used in the MPF payloads.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Sequence

import numpy as np
from imagecodecs import jpeg_encode

SOI = b"\xff\xd8"
APP1 = 0xFFE1
APP2 = 0xFFE2
ICC_PROFILE_LABEL = b"ICC_PROFILE\x00"

# Segment length field is 2 bytes and includes itself.
_MAX_SEGMENT_PAYLOAD = 65535 - 2
# Each ICC chunk carries the label plus 1-byte sequence/total counters.
_MAX_ICC_CHUNK = _MAX_SEGMENT_PAYLOAD - len(ICC_PROFILE_LABEL) - 2

_MPF_SIG = b"MPF\x00"
# Big-endian TIFF header: byte order, magic 42, offset to first IFD.
_MPF_TIFF_HEADER = b"MM\x00\x2a" + struct.pack(">I", 8)


def normalize_to_uint8(
    img_arr: np.ndarray, bit_depth: Optional[int] = None
) -> np.ndarray:
    """Rescale an image array to uint8 for JPEG encoding.

    Floats are treated as [0, 1]. Integer arrays deeper than 8 bits are
    rescaled from their `bit_depth` range (the dtype's full range when not
    given), so e.g. 10-bit 0..1023 or full-range 16-bit data maps to 0..255
    instead of being clipped. uint8 passes through unchanged.
    """
    if img_arr.dtype == np.uint8:
        return img_arr
    if np.issubdtype(img_arr.dtype, np.floating):
        return np.clip(np.round(img_arr * 255), 0, 255).astype(np.uint8)
    if bit_depth is None:
        bit_depth = img_arr.dtype.itemsize * 8
    if bit_depth <= 8:
        return np.clip(img_arr, 0, 255).astype(np.uint8)
    max_value = (1 << bit_depth) - 1
    scaled = np.round(img_arr.astype(np.float32) * (255.0 / max_value))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def encode_jpeg(img_arr: np.ndarray, quality: int = 95) -> bytes:
    """Encode a numpy array as baseline JPEG with 4:4:4 chroma subsampling.

    Accepts uint8, float ([0, 1] range) or deeper integer arrays (rescaled
    from the dtype's full range — use `normalize_to_uint8` first when the
    true bit depth is known), shaped (H, W), (H, W, 1), (H, W, 3) or
    (H, W, 4); single-channel input becomes grayscale JPEG and an alpha
    channel is dropped. No metadata segments are embedded — callers add
    ICC/MPF/XMP segments via `insert_segments`.
    """
    img_arr = normalize_to_uint8(img_arr)

    if img_arr.ndim == 3:
        if img_arr.shape[2] == 1:
            img_arr = img_arr[:, :, 0]
        elif img_arr.shape[2] == 4:
            img_arr = img_arr[:, :, :3]

    # jpeg_encode rejects non-contiguous input (e.g. the alpha-drop slice
    # above, or transposed/flipped caller arrays).
    img_arr = np.ascontiguousarray(img_arr)

    return jpeg_encode(img_arr, level=quality, subsampling="444")


def build_segment(marker: int, payload: bytes) -> bytes:
    """Build a JPEG marker segment: marker, length (incl. itself), payload."""
    if len(payload) > _MAX_SEGMENT_PAYLOAD:
        raise ValueError(
            f"JPEG segment payload too large: {len(payload)} > {_MAX_SEGMENT_PAYLOAD}"
        )
    return struct.pack(">HH", marker, len(payload) + 2) + payload


def build_icc_segments(icc: Optional[bytes]) -> List[bytes]:
    """Split an ICC profile into chunked APP2 segments (ICC.1 Annex B).

    Returns an empty list when `icc` is None or empty, so results can be
    spliced unconditionally into a segment list.
    """
    if not icc:
        return []

    chunks = [icc[i : i + _MAX_ICC_CHUNK] for i in range(0, len(icc), _MAX_ICC_CHUNK)]
    if len(chunks) > 255:
        raise ValueError(f"ICC profile too large to embed: {len(icc)} bytes")

    total = len(chunks)
    return [
        build_segment(APP2, ICC_PROFILE_LABEL + bytes((seq, total)) + chunk)
        for seq, chunk in enumerate(chunks, start=1)
    ]


def _header_insert_pos(jpeg: bytes) -> int:
    """Return the offset just past SOI and any leading APP0/APP1 segments.

    Inserting there keeps JFIF (APP0) and Exif (APP1) first, as their
    specifications require.
    """
    if jpeg[:2] != SOI:
        raise ValueError("Not a JPEG stream (missing SOI marker)")

    pos = 2
    while pos + 4 <= len(jpeg) and jpeg[pos] == 0xFF and jpeg[pos + 1] in (0xE0, 0xE1):
        pos += 2 + int.from_bytes(jpeg[pos + 2 : pos + 4], "big")
    return pos


def insert_segments(jpeg: bytes, segments: Sequence[bytes]) -> bytes:
    """Insert prebuilt marker segments into a JPEG stream's header area."""
    pos = _header_insert_pos(jpeg)
    return b"".join([jpeg[:pos], *segments, jpeg[pos:]])


def _mpf_tag(tag: int, type_: int, count: int, value: bytes) -> bytes:
    """Pack one 12-byte MPF IFD tag entry."""
    return struct.pack(">HHI", tag, type_, count) + value


def build_mpf_minimal_payload(num_images: int) -> bytes:
    """Build minimal MPF payload with Version and NumberOfImages only.

    Some implementations expect a minimal MPF APP2 in the gainmap stream.
    """
    ifd = (
        _mpf_tag(0xB000, 7, 4, b"0100")  # MPF Version, type UNDEFINED
        + _mpf_tag(0xB001, 4, 1, struct.pack(">I", num_images))  # type LONG
    )
    return b"".join(
        [
            _MPF_SIG,
            _MPF_TIFF_HEADER,
            struct.pack(">H", 2),  # tag count
            ifd,
            struct.pack(">I", 0),  # no next IFD
        ]
    )


def build_mpf_payload(
    primary_size: int, gainmap_size: int, gainmap_offset: int
) -> bytes:
    """Build MPF (Multi-Picture Format) index payload with 2 image entries.

    `gainmap_offset` is relative to the MPF TIFF header ("MM" bytes), per
    CIPA DC-007.
    """
    # MP Entry list: Attribute, Size, Offset, Dependent (16 bytes each).
    # Attributes are CIPA DC-007 type codes: 0x030000 primary, 0x050000 gainmap.
    entries = struct.pack(">IIII", 0x00030000, primary_size, 0, 0) + struct.pack(
        ">IIII", 0x00050000, gainmap_size, gainmap_offset, 0
    )
    ifd = (
        _mpf_tag(0xB000, 7, 4, b"0100")  # MPF Version
        + _mpf_tag(0xB001, 4, 1, struct.pack(">I", 2))  # NumberOfImages
        # MP Entry data sits right after the IFD:
        # TIFF header (8) + tag count (2) + 3 tags (36) + next-IFD (4) = 50.
        + _mpf_tag(0xB002, 7, len(entries), struct.pack(">I", 50))
    )
    return b"".join(
        [
            _MPF_SIG,
            _MPF_TIFF_HEADER,
            struct.pack(">H", 3),  # tag count
            ifd,
            struct.pack(">I", 0),  # no next IFD
            entries,
        ]
    )


def assemble_mpf_file(
    primary_jpeg: bytes,
    gainmap_stream: bytes,
    segments_before_mpf: Sequence[bytes],
    segments_after_mpf: Sequence[bytes],
) -> bytes:
    """Assemble a two-image MPF file: primary with MPF index, then gainmap.

    Inserts `segments_before_mpf`, the MPF index APP2 and
    `segments_after_mpf` into the primary stream's header area, then
    appends the (already finalized) gainmap stream. MPF offsets are
    computed exactly from the part lengths in a single pass; the MPF
    payload size does not depend on the values stored in it.
    """
    pos = _header_insert_pos(primary_jpeg)
    before = b"".join(segments_before_mpf)
    after = b"".join(segments_after_mpf)

    mpf_segment_len = len(build_segment(APP2, build_mpf_payload(0, 0, 0)))
    total_primary_len = len(primary_jpeg) + len(before) + mpf_segment_len + len(after)
    # MPF TIFF header sits after marker (2) + length (2) + "MPF\0" (4).
    mpf_header_offset = pos + len(before) + 8

    mpf_segment = build_segment(
        APP2,
        build_mpf_payload(
            primary_size=total_primary_len,
            gainmap_size=len(gainmap_stream),
            gainmap_offset=total_primary_len - mpf_header_offset,
        ),
    )
    return b"".join(
        [
            primary_jpeg[:pos],
            before,
            mpf_segment,
            after,
            primary_jpeg[pos:],
            gainmap_stream,
        ]
    )
