from hdrconv.core import HDRImage

from imagecodecs import avif_encode, avif_decode
import numpy as np


def read_22028_pq(filepath: str) -> HDRImage:
    """
    Read ISO 22028-5 PQ AVIF file.

    Args:
        filepath: Path to the PQ AVIF file

    Returns:
        HDRImage dict containing:
        - data: float32 array (H, W, 3), PQ-encoded, range [0, 1]
        - color_space: Color space identifier
        - transfer_function: 'pq' or 'hlg'
        - icc_profile: Optional ICC profile (currently not extracted)
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
    """
    Write ISO 22028-5 PQ AVIF file.

    Args:
        data: HDRImage dict with PQ-encoded data and parameters
        filepath: Output path for the AVIF file
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
