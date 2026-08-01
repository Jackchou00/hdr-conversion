"""HDR conversion algorithms.

This module provides functions for converting between HDR formats:

- Gainmap conversion: `gainmap_to_hdr`, `hdr_to_gainmap`
- Apple HEIC conversion: `apple_heic_to_hdr`

Transfer function encoding/decoding (e.g. PQ) is handled with the ``colour``
package, e.g. ``colour.eotf(data, 'ITU-R BT.2100 PQ')`` and
``colour.eotf_inverse(data, 'ITU-R BT.2100 PQ')`` as shown in ``examples/``.
"""

from hdrconv.convert.apple import apple_heic_to_hdr
from hdrconv.convert.gainmap import gainmap_to_hdr, hdr_to_gainmap


__all__ = [
    "gainmap_to_hdr",
    "hdr_to_gainmap",
    "apple_heic_to_hdr",
]
