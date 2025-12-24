"""HDR format I/O operations.

This module provides functions for reading and writing various HDR formats:

- ISO 21496-1 (Adaptive Gainmap): `read_21496`, `write_21496`
- ISO 22028-5 (PQ/HLG AVIF): `read_22028_pq`, `write_22028_pq`
- Apple HEIC with gainmap: `read_apple_heic`

"""

from .iso21496 import read_21496, write_21496

from .iso22028 import read_22028_pq, write_22028_pq

from .apple_heic import read_apple_heic

__all__ = [
    "read_21496",
    "write_21496",
    "read_22028_pq",
    "write_22028_pq",
    "read_apple_heic",
]
