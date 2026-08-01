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


# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def _heif_image_to_uint8_array(image) -> np.ndarray:
    """Convert a pillow_heif image (main or auxiliary) to a uint8 numpy array.

    pillow_heif returns 10/12-bit HEIC data as 16-bit modes ('RGB;16',
    'RGBA;16', 'L;16') scaled to the full 16-bit range. These are raw-decoder
    modes that PIL's Image.frombytes rejects, so they are parsed with numpy
    (respecting the row stride) and downshifted to 8 bits.
    """
    mode = image.mode
    if mode.endswith(";16"):
        channels = {"RGB;16": 3, "RGBA;16": 4, "L;16": 1}.get(mode)
        if channels is None:
            raise ValueError(f"Unsupported HEIF image mode: {mode}")
        width, height = image.size
        arr = np.frombuffer(image.data, dtype=np.uint16).reshape(
            height, image.stride // 2
        )[:, : width * channels]
        if channels > 1:
            arr = arr.reshape(height, width, channels)
        # 10/12-bit data is scaled to the full 16-bit range, so the top
        # 8 bits carry the image content.
        return (arr >> 8).astype(np.uint8)

    pil_image = Image.frombytes(
        mode,
        image.size,
        image.data,
        "raw",
        mode,
        image.stride,
    )
    return np.array(pil_image)


def _read_base_gain_map_and_icc(
    input_path: str,
) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[bytes]]:
    """Read the Apple HEIC base image, gain map, and embedded ICC profile."""
    try:
        heif_file = pillow_heif.read_heif(input_path, convert_hdr_to_8bit=False)
    except Exception as e:
        print(f"Error: Unable to read HEIC file '{input_path}': {e}")
        raise

    # Base Image
    base_image_np = _heif_image_to_uint8_array(heif_file)

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
                gain_map_np = _heif_image_to_uint8_array(aux_image)
            except Exception as e:
                # Handle rare cases where the ID exists but the image data cannot be extracted
                print(f"Warning: Unable to extract gain map with ID {gain_map_id}: {e}")

    return base_image_np, gain_map_np, heif_file.info.get("icc_profile")


def read_base_and_gain_map(input_path: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Read the base image and HDR gain map from an Apple HEIC file.

    The gain map is typically one-quarter the base image resolution and is
    single-channel. This compatibility wrapper intentionally omits color
    metadata; ``read_apple_heic`` retains it for the conversion pipeline.
    """
    base, gainmap, _ = _read_base_gain_map_and_icc(input_path)
    return base, gainmap


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

    Apple uses headroom instead of GainMap Min and Max.
    Formula: hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

    Args:
        file_path: Path to the HEIC file.
        use_makernote: If True, prefer MakerNotes over XMP metadata.

    Returns:
        HDR headroom value (peak luminance ratio).

    Raises:
        RuntimeError: If exiftool is not installed.
        ValueError: If neither XMP nor MakerNotes headroom metadata is found.

    See Also:
        - https://developer.apple.com/documentation/appkit/applying-apple-hdr-effect-to-your-photos
        - https://github.com/johncf/apple-hdr-heic (metadata extraction reference)
    """
    _check_exiftool_installed()

    target_tags = [
        "XMP:HDRGainMapHeadroom",
        "MakerNotes:HDRHeadroom",
        "MakerNotes:HDRGain",
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

    if maker33 is None or maker48 is None:
        # MakerNotes missing: fall back to XMP if available (mirror of the
        # XMP-preferred path falling back to MakerNotes above).
        if "XMP:HDRGainMapHeadroom" in metadata:
            return float(metadata["XMP:HDRGainMapHeadroom"])
        raise ValueError(
            "Cannot extract HDR headroom: neither XMP:HDRGainMapHeadroom nor "
            "MakerNotes:HDRHeadroom/HDRGain found in file metadata."
        )

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

    base, gainmap, icc_profile = _read_base_gain_map_and_icc(filepath)
    headroom = get_headroom(filepath)

    if base is None or gainmap is None or headroom is None:
        raise ValueError(f"Failed to read Apple HEIC data from {filepath}")

    return AppleHeicData(
        base=base, gainmap=gainmap, headroom=headroom, icc_profile=icc_profile
    )
