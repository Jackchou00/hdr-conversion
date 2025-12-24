"""Core data structures for HDR conversion.

This module contains the TypedDict-based structures used across the library.
"""

from __future__ import annotations

from typing import Optional, Tuple, TypedDict

import numpy as np


class GainmapMetadata(TypedDict, total=False):
    """ISO 21496-1 Gainmap metadata following the standard.

    All fields use standard names from the specification.
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
    """Gainmap image representation.

    Contains baseline (SDR) image, gainmap, and metadata.
    """

    # Baseline image: uint8, shape (H, W, 3), range [0, 255]
    baseline: np.ndarray

    # Gainmap: uint8, shape (H, W, 3) or (H, W, 1), range [0, 255]
    gainmap: np.ndarray

    # Gainmap transformation metadata
    metadata: GainmapMetadata

    # Optional ICC profiles
    baseline_icc: Optional[bytes]
    gainmap_icc: Optional[bytes]


class HDRImage(TypedDict):
    """HDR image representation.

    Linear RGB data with metadata.
    """

    # Image data: float32, shape (H, W, 3)
    # Values in linear light, range typically [0, max_luminance/10000]
    # For PQ/HLG, this should be normalized appropriately
    data: np.ndarray

    # Color space identifier: 'bt709', 'p3', 'bt2020'
    color_space: str

    # Transfer function: 'linear', 'pq', 'hlg', 'srgb'
    transfer_function: str

    # Optional ICC profile
    icc_profile: Optional[bytes]


class AppleHeicData(TypedDict):
    """Apple HEIC HDR image data.

    Contains base image, gainmap, and headroom metadata.
    """

    # Base image: uint8, shape (H, W, 3), Display P3 color space
    base: np.ndarray

    # Gainmap: uint8, shape (H, W, 1), single channel
    gainmap: np.ndarray

    # Headroom value for gain calculation
    headroom: float
