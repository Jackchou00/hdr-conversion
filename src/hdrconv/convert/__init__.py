"""HDR conversion algorithms.

This module provides functions for converting between HDR formats and applying
color space and transfer function transformations:

- Gainmap conversion: `gainmap_to_hdr`, `hdr_to_gainmap`
- Apple HEIC conversion: `apple_heic_to_hdr`
- Color space conversion: `convert_color_space`
- Transfer functions: `apply_pq`, `inverse_pq`
"""

from hdrconv.convert.apple import apple_heic_to_hdr
from hdrconv.convert.colorspace import convert_color_space
from hdrconv.convert.gainmap import gainmap_to_hdr, hdr_to_gainmap
from hdrconv.convert.transfer import apply_pq, inverse_pq

__all__ = [
    "gainmap_to_hdr",
    "hdr_to_gainmap",
    "apple_heic_to_hdr",
    "convert_color_space",
    "apply_pq",
    "inverse_pq",
]
