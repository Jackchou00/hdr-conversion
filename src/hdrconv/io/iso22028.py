"""ISO 22028-5 PQ/HLG AVIF I/O operations.

This module provides functions for reading and writing ISO 22028-5 compliant
HDR AVIF files.

ISO 22028-5 specifies encoding of HDR images using HEIF/AVIF container
with BT.2100 transfer characteristics (PQ or HLG).

Public APIs:
    - `read_22028_pq`: Read PQ AVIF to HDRImage
    - `write_22028_pq`: Write HDRImage to PQ AVIF
"""

import inspect
import struct

from hdrconv.core import HDRImage

from imagecodecs import avif_encode, avif_decode
import numpy as np


try:
    _AVIF_ENCODE_SUPPORTS_MATRIX = (
        "matrix" in inspect.signature(avif_encode).parameters
    )
except (TypeError, ValueError):  # pragma: no cover - signature not introspectable
    _AVIF_ENCODE_SUPPORTS_MATRIX = False


def _iter_boxes(data: bytes, start: int, end: int):
    """Yield (box_type, payload_start, payload_end) for ISOBMFF boxes in [start, end)."""
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        box_type = data[pos + 4 : pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield box_type, pos + header, pos + size
        pos += size


def _find_ipco(avif_bytes: bytes) -> tuple[int, int] | None:
    """Locate the ipco (item property container) box payload in an AVIF file."""
    for box_type, start, end in _iter_boxes(avif_bytes, 0, len(avif_bytes)):
        if box_type == b"meta":
            # meta is a FullBox: skip 4 bytes of version/flags
            for sub_type, sub_start, sub_end in _iter_boxes(avif_bytes, start + 4, end):
                if sub_type == b"iprp":
                    for prop_type, prop_start, prop_end in _iter_boxes(
                        avif_bytes, sub_start, sub_end
                    ):
                        if prop_type == b"ipco":
                            return prop_start, prop_end
    return None


def _parse_avif_bit_depth(avif_bytes: bytes) -> int | None:
    """Parse the coded bit depth from the av1C box, or None if not found."""
    ipco = _find_ipco(avif_bytes)
    if ipco is None:
        return None
    for box_type, start, end in _iter_boxes(avif_bytes, ipco[0], ipco[1]):
        if box_type == b"av1C" and end - start >= 3:
            flags = avif_bytes[start + 2]
            high_bitdepth = (flags >> 6) & 1
            twelve_bit = (flags >> 5) & 1
            if not high_bitdepth:
                return 8
            return 12 if twelve_bit else 10
    return None


def _parse_avif_primaries(avif_bytes: bytes) -> int | None:
    """Parse the nclx colour primaries code from the colr box, or None if not found."""
    ipco = _find_ipco(avif_bytes)
    if ipco is None:
        return None
    for box_type, start, end in _iter_boxes(avif_bytes, ipco[0], ipco[1]):
        if (
            box_type == b"colr"
            and avif_bytes[start : start + 4] == b"nclx"
            and end - start >= 6
        ):
            return struct.unpack(">H", avif_bytes[start + 4 : start + 6])[0]
    return None


def read_22028_pq(filepath: str) -> HDRImage:
    """Read ISO 22028-5 PQ AVIF file.

    Decodes an AVIF file encoded with Perceptual Quantizer (PQ) transfer
    function as specified in ISO 22028-5 and SMPTE ST 2084.

    Args:
        filepath: Path to the PQ AVIF file.

    Returns:
        HDRImage dict containing:
        - ``data`` (np.ndarray): PQ-encoded array, float32, shape (H, W, 3),
            range [0, 1] representing 0-10000 nits.
        - ``color_space`` (str): Color primaries parsed from the file's nclx
            colr box ('bt709', 'p3', or 'bt2020'; defaults to 'bt2020').
        - ``transfer_function`` (str): Always 'pq'.
        - ``icc_profile`` (bytes | None): Currently None (not extracted).

    Note:
        Sample values are normalized using the actual coded bit depth
        (8, 10, or 12), parsed from the file's av1C box. If the depth
        cannot be determined for 16-bit samples, 10-bit is assumed.

    See Also:
        - `write_22028_pq`: Write HDR image to PQ AVIF format.
        - ``colour.eotf(data, 'ITU-R BT.2100 PQ')``: Convert PQ-encoded
            data to linear light (see ``examples/pq_to_gainmap.py``).
    """
    with open(filepath, "rb") as f:
        avif_bytes = f.read()
    image_array = avif_decode(avif_bytes, numthreads=-1)
    # Normalize samples to [0, 1] using the actual coded bit depth.
    if image_array.dtype == np.uint8:
        bit_depth = 8
    else:
        bit_depth = _parse_avif_bit_depth(avif_bytes)
        if bit_depth not in (10, 12):
            # Fall back to the most common HDR AVIF depth.
            bit_depth = 10
    image_array = (image_array / float((1 << bit_depth) - 1)).astype(np.float32)

    color_space_map = {1: "bt709", 9: "bt2020", 12: "p3"}
    color_space = color_space_map.get(_parse_avif_primaries(avif_bytes), "bt2020")
    return HDRImage(
        data=image_array,
        color_space=color_space,
        transfer_function="pq",
        icc_profile=None,
    )


def write_22028_pq(data: HDRImage, filepath: str) -> None:
    """Write ISO 22028-5 PQ AVIF file.

    Encodes an HDR image to AVIF format with Perceptual Quantizer (PQ)
    transfer function as specified in ISO 22028-5 and SMPTE ST 2084.

    Args:
        data: HDRImage dict with PQ-encoded data. Must contain:
            - ``data``: float32 array, shape (H, W, 3), range [0, 1].
            - ``transfer_function``: Transfer function ('pq', 'hlg', etc.).
            May contain:
            - ``color_space``: Color primaries ('bt709', 'p3', 'bt2020').
                Defaults to 'bt2020'.
        filepath: Output path for the AVIF file.

    Note:
        Output is encoded at 10-bit depth with quality level 90.
        Color primaries and transfer characteristics are embedded in AVIF metadata.

    See Also:
        - `read_22028_pq`: Read PQ AVIF file.
        - ``colour.eotf_inverse(data, 'ITU-R BT.2100 PQ')``: Convert linear
            HDR to PQ-encoded values (see ``examples/gainmap_to_pq.py``).
    """
    # Map color primaries to numeric codes
    primaries_map = {"bt709": 1, "bt2020": 9, "p3": 12}

    # Map transfer characteristics to numeric codes
    transfer_map = {"bt709": 1, "linear": 8, "pq": 16, "hlg": 18}

    primaries_code = primaries_map.get(data.get("color_space", "bt2020"), 9)
    transfer_code = transfer_map.get(data["transfer_function"], 16)

    np_array = np.clip(data["data"], 0, 1)
    # scale to [0, 1023]
    np_array = np.round(np_array * 1023.0)
    np_array = np_array.astype(np.uint16)

    encode_kwargs = dict(
        level=90,
        speed=8,
        bitspersample=10,
        primaries=primaries_code,
        transfer=transfer_code,
        numthreads=-1,
    )
    if _AVIF_ENCODE_SUPPORTS_MATRIX:
        # BT.2020 non-constant luminance (CICP matrix 9), per ISO 22028-5.
        encode_kwargs["matrix"] = 9

    avif_bytes: bytes = avif_encode(np_array, **encode_kwargs)

    # Write the AVIF bytes to the output file
    with open(filepath, "wb") as f:
        f.write(avif_bytes)
