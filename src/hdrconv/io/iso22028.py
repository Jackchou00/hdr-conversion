from hdrconv.core import PQImage

from imagecodecs import avif_encode, avif_decode
import numpy as np


def read_22028_pq(filepath: str) -> PQImage:
    """
    Read ISO 22028-5 PQ AVIF file.

    Args:
        filepath: Path to the PQ AVIF file

    Returns:
        PQImage dict containing:
        - data: float32 array (H, W, 3), PQ-encoded, range [0, 1]
        - color_primaries: Color space identifier
        - transfer_characteristics: 'pq' or 'hlg'
        - bit_depth: 10 or 12
    """
    with open(filepath, "rb") as f:
        avif_bytes = f.read()
    image_array = avif_decode(avif_bytes, numthreads=-1)
    # Extract PQ-encoded array (normalized to [0, 1])
    image_array = image_array / 1023.0
    # TODO: Extract actual color primaries and transfer from AVIF metadata
    # For now, assume BT.2020 PQ which is most common
    return PQImage(
        data=image_array,
        color_primaries="bt2020",
        transfer_characteristics="pq",
        bit_depth=10,
    )


def write_22028_pq(data: PQImage, filepath: str) -> None:
    """
    Write ISO 22028-5 PQ AVIF file.

    Args:
        data: PQImage dict with PQ-encoded data and parameters
        filepath: Output path for the AVIF file
    """
    # Map color primaries to numeric codes
    primaries_map = {"bt709": 1, "bt2020": 9, "p3": 12}

    # Map transfer characteristics to numeric codes
    transfer_map = {"bt709": 1, "linear": 8, "pq": 16, "hlg": 18}

    primaries_code = primaries_map.get(data["color_primaries"], 9)
    transfer_code = transfer_map.get(data["transfer_characteristics"], 16)

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
