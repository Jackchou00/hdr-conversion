"""Apple HEIC HDR format identification.

This module provides functions for detecting HDR content in Apple HEIC files
by checking for the presence of gain map auxiliary images.

Apple stores HDR gain maps with the URN:
    urn:com:apple:photo:2020:aux:hdrgainmap

Public APIs:
    - `has_gain_map`: Check if HEIC file contains HDR gain map
"""

import pillow_heif


# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def has_gain_map(input_path: str) -> bool:
    """Check if Apple HEIC file contains HDR gain map.

    Scans the auxiliary images in a HEIC file to detect the presence of
    Apple's HDR gain map (URN: urn:com:apple:photo:2020:aux:hdrgainmap).

    Args:
        input_path: Path to the input HEIC image file.

    Returns:
        True if an HDR gain map auxiliary image is found, False otherwise.

    Note:
        This function does not validate the gain map data itself, only
        checks for its presence in the file metadata.

    See Also:
        - `read_apple_heic`: Extract gain map data from HEIC file.
    """
    has_gain_map = False
    heif_file = pillow_heif.read_heif(input_path, convert_hdr_to_8bit=False)

    if "aux" in heif_file.info:
        aux_info = heif_file.info["aux"]
        for urn, ids in aux_info.items():
            # print(f"  URN: {urn}, IDs: {ids}")
            if urn == HDR_GAIN_MAP_URN:
                has_gain_map = True
    return has_gain_map
