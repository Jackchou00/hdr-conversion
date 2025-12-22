"""
I/O Module for HDR Image Formats

This module provides functions for reading and writing various HDR image formats:
- ISO 21496-1 Gainmap (read_21496, write_21496)
- ISO 22028-5 PQ AVIF (read_22028_pq, write_22028_pq)
- Apple HEIC HDR (read_apple_heic)

Example:
    >>> import hdrconv.io as io
    >>>
    >>> # Read ISO 21496-1 Gainmap
    >>> gainmap = io.read_21496("gainmap.jpg")
    >>>
    >>> # Read Apple HEIC
    >>> heic_data = io.read_apple_heic("IMG_1234.HEIC")
    >>>
    >>> # Read PQ AVIF
    >>> pq_data = io.read_22028_pq("hdr.avif")
    >>>
    >>> # Write formats
    >>> io.write_21496(gainmap, "output.jpg")
    >>> io.write_22028_pq(pq_data, "output.avif")
"""

# ISO 21496-1 Gainmap I/O
from .iso21496 import (
    read_21496,
    write_21496,
)

# ISO 22028-5 PQ AVIF I/O
from .iso22028 import (
    read_22028_pq,
    write_22028_pq,
)

# Apple HEIC HDR I/O
from .apple_heic import (
    read_apple_heic,
    read_base_and_gain_map,
    get_headroom,
)

__all__ = [
    # ISO 21496-1 Gainmap
    "read_21496",
    "write_21496",
    # ISO 22028-5 PQ AVIF
    "read_22028_pq",
    "write_22028_pq",
    # Apple HEIC HDR
    "read_apple_heic",
    "read_base_and_gain_map",
    "get_headroom",
]
