"""Apple HEIC HDR format I/O operations.

This module provides functions for reading Apple's proprietary HDR format
from iPhone HEIC photos, which contains a base SDR image and a single-channel
gain map as an auxiliary image.

Public APIs:
    - `read_apple_heic`: Read HEIC file to AppleHeicData

The gain map uses Apple's URN (urn:com:apple:photo:2020:aux:hdrgainmap) and
is stored at 1/4 resolution of the main image.

Note:
    Requires exiftool to be installed for headroom metadata extraction.
"""

import shutil
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
    """Read base image and HDR gain map from Apple HEIC file.

    Extracts the primary image and the auxiliary HDR gain map identified
    by Apple's proprietary URN from a HEIC file.

    Args:
        input_path: Path to the input HEIC image file.

    Returns:
        Tuple of (base_image, gain_map) where:
        - ``base_image`` (np.ndarray): Main image, uint8/uint16, shape (H, W, 3).
        - ``gain_map`` (np.ndarray | None): Gain map if found, shape (H, W),
            or None if no HDR gain map auxiliary image exists.

    Raises:
        Exception: If the HEIC file cannot be read.

    Note:
        The gain map is typically at 1/4 resolution of the base image
        and uses a single grayscale channel.
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


def _check_exiftool_installed() -> None:
    """Check if exiftool is installed and accessible.

    Raises:
        RuntimeError: If exiftool is not found in PATH.
    """
    if shutil.which("exiftool") is None:
        raise RuntimeError(
            "exiftool is not installed or not found in PATH. "
            "Please install exiftool:\n"
            "  - macOS: brew install exiftool\n"
            "  - Ubuntu/Debian: sudo apt-get install libimage-exiftool-perl\n"
            "  - Windows: Download from https://exiftool.org/"
        )


def get_headroom(file_path: str | Path, use_makernote: bool = False) -> float:
    """Extract HDR headroom from Apple HEIC metadata.

    Args:
        file_path: Path to the HEIC file.
        use_makernote: If True, prefer MakerNotes over XMP metadata.

    Returns:
        HDR headroom value (peak luminance ratio).

    Raises:
        RuntimeError: If exiftool is not installed.
    """
    _check_exiftool_installed()

    target_tags = [
        "XMP:HDRGainMapHeadroom",
        "MakerNotes:HDRHeadroom",  #  maker33
        "MakerNotes:HDRGain",  #  maker48
    ]

    try:
        with ExifToolHelper() as et:
            metadata = et.get_tags(file_path, tags=target_tags)[0]
    except FileNotFoundError as e:
        raise RuntimeError(
            "exiftool executable not found. Please ensure exiftool is installed "
            "and accessible in your PATH."
        ) from e

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
    """Read Apple HEIC HDR file with gain map.

    Extracts the base SDR image, HDR gain map, and headroom metadata from
    iPhone HEIC photos containing Apple's proprietary HDR format.

    Args:
        filepath: Path to the Apple HEIC file.

    Returns:
        AppleHeicData dict containing:
        - ``base`` (np.ndarray): SDR image, uint8, shape (H, W, 3), Display P3.
        - ``gainmap`` (np.ndarray): Gain map, uint8, shape (H, W, 1), 1/4 resolution.
        - ``headroom`` (float): Peak luminance headroom, typically 2.0-8.0.

    Raises:
        ValueError: If base image, gainmap, or headroom cannot be extracted.

    Note:
        Requires exiftool to be installed and accessible in PATH for
        headroom extraction from EXIF/MakerNotes metadata.

    See Also:
        - `apple_heic_to_hdr`: Convert AppleHeicData to linear HDR.
        - `has_gain_map`: Check if HEIC file contains gain map.
    """

    base, gainmap = read_base_and_gain_map(filepath)
    headroom = get_headroom(filepath)

    if base is None or gainmap is None or headroom is None:
        raise ValueError(f"Failed to read Apple HEIC data from {filepath}")

    return AppleHeicData(base=base, gainmap=gainmap, headroom=headroom)
