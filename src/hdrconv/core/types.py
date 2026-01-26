"""Core data structures for HDR conversion.

This module contains the TypedDict-based structures used across the library.
"""

from __future__ import annotations

from typing import Optional, Tuple, TypedDict

import numpy as np


class GainmapMetadata(TypedDict, total=False):
    """ISO 21496-1 Gainmap metadata structure.

    Contains transformation parameters for converting between baseline (SDR)
    and alternate (HDR) representations as defined in ISO 21496-1.

    Attributes:
        minimum_version: Minimum decoder version required. Should be 0.
        writer_version: Version of the encoder that created the metadata.
        baseline_hdr_headroom: HDR headroom of baseline image, typically 1.0.
        alternate_hdr_headroom: HDR headroom of alternate image (e.g., 4.5).
        is_multichannel: True if gainmap has separate RGB channels, False for single channel.
        use_base_colour_space: True to compute in baseline color space, False for alternate.
        gainmap_min: Minimum gainmap values per channel, tuple of 3 floats.
        gainmap_max: Maximum gainmap values per channel, tuple of 3 floats.
        gainmap_gamma: Gamma values per channel for gainmap decoding, tuple of 3 floats.
        baseline_offset: Offset added to baseline before multiplication, tuple of 3 floats.
        alternate_offset: Offset subtracted from result, tuple of 3 floats.

    """

    # Version information
    minimum_version: int
    writer_version: int

    # HDR headroom values
    baseline_hdr_headroom: float
    alternate_hdr_headroom: float

    # Channel configuration
    is_multichannel: bool
    use_base_colour_space: bool

    # Gainmap transformation parameters (RGB triplets)
    gainmap_min: Tuple[float, float, float]
    gainmap_max: Tuple[float, float, float]
    gainmap_gamma: Tuple[float, float, float]

    # Offset parameters (RGB triplets)
    baseline_offset: Tuple[float, float, float]
    alternate_offset: Tuple[float, float, float]


class GainmapImage(TypedDict):
    """ISO 21496-1 Gainmap image structure.

    Contains the baseline (SDR) image, gainmap, and associated metadata
    required for HDR reconstruction using the ISO 21496-1 formula.

    Attributes:
        baseline: SDR image array, uint8, shape (H, W, 3), range [0, 255].
            Typically sRGB-encoded Display P3 or BT.709 content.
        gainmap: Gain map array, uint8, shape (H, W, 3) or (H, W, 1),
            range [0, 255]. Encodes the HDR-to-SDR ratio in log2 space.
        metadata: GainmapMetadata dict containing transformation parameters
            such as gamma, min/max values, and offsets.
        baseline_icc: Optional ICC profile bytes for baseline image color space.
        gainmap_icc: Optional ICC profile bytes for gainmap color space.

    See Also:
        - `read_21496`: Read GainmapImage from ISO 21496-1 JPEG file.
        - `gainmap_to_hdr`: Convert GainmapImage to linear HDR.
    """

    baseline: np.ndarray
    gainmap: np.ndarray
    metadata: GainmapMetadata
    baseline_icc: Optional[bytes]
    gainmap_icc: Optional[bytes]


class HDRImage(TypedDict):
    """HDR image representation with color metadata.

    Contains linear or transfer-encoded RGB data with associated color space
    and transfer function information for proper display and conversion.

    Attributes:
        data: Image data array, float32, shape (H, W, 3).
            For linear transfer: values in linear light, range [0, peak_luminance/reference_white].
            For PQ transfer: values in range [0, 1] representing 0-10000 nits.
            For HLG transfer: values in range [0, 1] representing scene-referred light.
        color_space: Color primaries identifier.
            Options: 'bt709' (Rec. 709), 'p3' (Display P3), 'bt2020' (Rec. 2020).
        transfer_function: Transfer function applied to the data.
            Options: 'linear', 'pq' (SMPTE ST 2084), 'hlg' (ITU-R BT.2100), 'srgb'.
        icc_profile: Optional ICC profile bytes for custom color space definition.

    See Also:
        - `gainmap_to_hdr`: Create HDRImage from GainmapImage.
        - `apply_pq`: Apply PQ transfer function to linear HDRImage.
    """

    data: np.ndarray
    color_space: str
    transfer_function: str
    icc_profile: Optional[bytes]


class AppleHeicData(TypedDict):
    """Apple HEIC HDR image data structure.

    Contains the base (SDR) image, single-channel gainmap, and headroom value
    used by Apple's proprietary HDR gain map format in iPhone photos.

    The HDR reconstruction formula is:
        hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

    Attributes:
        base: Base SDR image array, uint8, shape (H, W, 3), range [0, 255].
            Encoded in Display P3 color space with sRGB transfer function.
        gainmap: Gain map array, uint8, shape (H, W, 1), range [0, 255].
            Single-channel map at 1/4 resolution of base image.
            Uses Rec. 709 transfer function internally.
        headroom: Peak luminance headroom value, typically 2.0-8.0.
            Represents the maximum brightness multiplier for HDR highlights.

    See Also:
        - `read_apple_heic`: Read AppleHeicData from HEIC file.
        - `apple_heic_to_hdr`: Convert AppleHeicData to linear HDRImage.
    """

    base: np.ndarray
    gainmap: np.ndarray
    headroom: float
