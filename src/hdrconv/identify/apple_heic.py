"""
Identify all aux images from HEIC files shot by iPhone.

Modified from: https://github.com/finnschi/heic-shenanigans/blob/main/gain_map_extract.py

iPhone's Gainmap is an auxiliary image with 1/4 the resolution of the main image and a single channel.
"""

import pillow_heif


# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def has_gain_map(input_path: str) -> bool:
    """
    Checks if a HEIC file contains auxiliary images and prints all auxiliary image IDs.

    This function reads a HEIC file, prints all found auxiliary image IDs,
    and returns True if auxiliary images are present, False otherwise.

    Args:
        input_path (str): Path to the input HEIC image file.

    Returns:
        bool: True if auxiliary images are found, False otherwise.
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
