import pillow_heif
import numpy as np
from PIL import Image
from typing import Tuple, Optional
from pathlib import Path
from exiftool import ExifToolHelper

from hdrconv.core import AppleHeicData


"""
Extracts main image and gainmap from HEIC files shot by iPhone.

Modified from: https://github.com/finnschi/heic-shenanigans/blob/main/gain_map_extract.py

iPhone's Gainmap is an auxiliary image with 1/4 the resolution of the main image and a single channel.
"""


# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def read_base_and_gain_map(input_path: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Reads the base image and HDR gain map from a HEIC file and returns them as NumPy arrays.

    This function specifically looks for the auxiliary image identified by the URN
    'urn:com:apple:photo:2020:aux:hdrgainmap' as the gain map.

    Args:
        input_path (str): Path to the input HEIC image file.

    Returns:
        A tuple containing two elements (base_image, gain_map):
        - base_image (np.ndarray): NumPy array of the main image.
        - gain_map (np.ndarray | None): NumPy array of the HDR gain map.
    """
    try:
        heif_file = pillow_heif.read_heif(input_path, convert_hdr_to_8bit=False)
    except Exception as e:
        print(f"Error: Unable to read HEIC file '{input_path}': {e}")
        raise

    # Base Image
    base_image_pil = Image.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    base_image_np = np.array(base_image_pil)

    # Gain Map
    gain_map_np = None  # Default to None if not found

    # Check if 'aux' metadata exists and if our desired URN is one of its keys
    if "aux" in heif_file.info and HDR_GAIN_MAP_URN in heif_file.info["aux"]:
        gain_map_ids = heif_file.info["aux"][HDR_GAIN_MAP_URN]

        if gain_map_ids:
            try:
                # Take the first ID from the list
                gain_map_id = gain_map_ids[0]
                # Use the ID to get the auxiliary image object
                aux_image = heif_file.get_aux_image(gain_map_id)

                # Create a PIL.Image object from the raw data, mode, size, and stride
                gain_map_pil = Image.frombytes(
                    aux_image.mode,
                    aux_image.size,
                    aux_image.data,
                    "raw",
                    aux_image.mode,
                    aux_image.stride,
                )
                gain_map_np = np.array(gain_map_pil)
            except Exception as e:
                # Handle rare cases where the ID exists but the image data cannot be extracted
                print(f"Warning: Unable to extract gain map with ID {gain_map_id}: {e}")

    return base_image_np, gain_map_np


"""
Apple uses headroom, instead of GainMap Min and Max.

Reference: https://developer.apple.com/documentation/appkit/applying-apple-hdr-effect-to-your-photos

e.g. hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

rgb and gainmap here all in linear space, gainmap defaultly use a Rec.709 transfer function.

Code below shows how to extract the "headroom" from a file's EXIF part.

Original code: https://github.com/johncf/apple-hdr-heic/blob/master/src/apple_hdr_heic/metadata.py
"""


def get_headroom(file_path: str | Path, use_makernote: bool = False) -> float:
    target_tags = [
        "XMP:HDRGainMapHeadroom",
        "MakerNotes:HDRHeadroom",  #  maker33
        "MakerNotes:HDRGain",  #  maker48
    ]

    with ExifToolHelper() as et:
        metadata = et.get_tags(file_path, tags=target_tags)[0]

    if "XMP:HDRGainMapHeadroom" in metadata and not use_makernote:
        return float(metadata["XMP:HDRGainMapHeadroom"])

    maker33 = metadata.get("MakerNotes:HDRHeadroom")
    maker48 = metadata.get("MakerNotes:HDRGain")

    if maker33 < 1.0:
        if maker48 <= 0.01:
            stops = -20.0 * maker48 + 1.8
        else:
            stops = -0.101 * maker48 + 1.601
    else:
        if maker48 <= 0.01:
            stops = -70.0 * maker48 + 3.0
        else:
            stops = -0.303 * maker48 + 2.303

    headroom = 2.0 ** max(stops, 0.0)
    return headroom


def read_apple_heic(filepath: str) -> AppleHeicData:
    """
    Read Apple HEIC HDR file.

    Args:
        filepath: Path to the Apple HEIC file

    Returns:
        AppleHeicData dict containing:
        - base: uint8 array (H, W, 3), Display P3, range [0, 255]
        - gainmap: uint8 array (H, W, 1), single channel, range [0, 255]
        - headroom: float, gain headroom value
    """

    base, gainmap = read_base_and_gain_map(filepath)
    headroom = get_headroom(filepath)

    if base is None or gainmap is None or headroom is None:
        raise ValueError(f"Failed to read Apple HEIC data from {filepath}")

    return AppleHeicData(base=base, gainmap=gainmap, headroom=headroom)
