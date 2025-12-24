"""Core data types for HDR conversion.

This module contains the TypedDict-based structures shared across the library
for representing HDR images, gainmaps, and associated metadata.

Public Types:
    - `GainmapImage`: ISO 21496-1 gainmap container
    - `GainmapMetadata`: Gainmap transformation parameters
    - `HDRImage`: Linear or transfer-encoded HDR image
    - `AppleHeicData`: Apple HEIC gainmap container
"""

from .types import AppleHeicData, GainmapImage, GainmapMetadata, HDRImage

__all__ = [
    "AppleHeicData",
    "GainmapImage",
    "GainmapMetadata",
    "HDRImage",
]
