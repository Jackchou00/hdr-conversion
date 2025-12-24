"""ISO 22028-5 PQ/HLG AVIF I/O operations.

This module provides functions for reading and writing ISO 22028-5 compliant
HDR AVIF files using Perceptual Quantizer (PQ) transfer function.

ISO 22028-5 specifies encoding of HDR images using HEIF/AVIF container
with BT.2100 transfer characteristics (PQ or HLG).

Public APIs:
    - `read_22028_pq`: Read PQ AVIF to HDRImage
    - `write_22028_pq`: Write HDRImage to PQ AVIF

Note:
    Requires imagecodecs library with AVIF support (libavif).
"""

from hdrconv.core import HDRImage

from imagecodecs import avif_encode, avif_decode
import numpy as np


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
            - ``color_space`` (str): Color primaries, typically 'bt2020'.
            - ``transfer_function`` (str): Always 'pq'.
            - ``icc_profile`` (bytes | None): Currently None (not extracted).

        Note:
            Currently assumes BT.2020 color primaries and 10-bit decode range.
            Future versions may extract actual color metadata from AVIF.

        See Also:
            - `write_22028_pq`: Write HDR image to PQ AVIF format.
            - `inverse_pq`: Convert PQ-encoded data to linear light.
    """
    with open(filepath, "rb") as f:
        avif_bytes = f.read()
    image_array = avif_decode(avif_bytes, numthreads=-1)
    # Extract PQ-encoded array (normalized to [0, 1])
    # Currently hard-coded to 10-bit decode range.
    image_array = image_array / 1023.0
    # TODO: Extract actual color primaries and transfer from AVIF metadata
    # For now, assume BT.2020 PQ which is most common
    return HDRImage(
        data=image_array,
        color_space="bt2020",
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
                - ``color_space``: Color primaries ('bt709', 'p3', 'bt2020').
                - ``transfer_function``: Transfer function ('pq', 'hlg', etc.).
            filepath: Output path for the AVIF file.

        Note:
            Output is encoded at 10-bit depth with quality level 90.
            Color primaries and transfer characteristics are embedded in AVIF metadata.

        See Also:
            - `read_22028_pq`: Read PQ AVIF file.
            - `apply_pq`: Convert linear HDR to PQ-encoded values.
    """
    # Map color primaries to numeric codes
    primaries_map = {"bt709": 1, "bt2020": 9, "p3": 12}

    # Map transfer characteristics to numeric codes
    transfer_map = {"bt709": 1, "linear": 8, "pq": 16, "hlg": 18}

    primaries_code = primaries_map.get(data["color_space"], 9)
    transfer_code = transfer_map.get(data["transfer_function"], 16)

    np_array = np.clip(data["data"], 0, 1)
    # scale to [0, 1023]
    np_array = np_array * 1023.0
    np_array = np_array.astype(np.uint16)

    avif_bytes: bytes = avif_encode(
        np_array,
        level=90,
        speed=8,
        bitspersample=10,
        primaries=primaries_code,
        transfer=transfer_code,
        numthreads=-1,
    )

    # Write the AVIF bytes to the output file
    with open(filepath, "wb") as f:
        f.write(avif_bytes)
