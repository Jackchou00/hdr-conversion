"""HDR conversion research library.

Public usage is via submodules (two-level imports), e.g.:
    - ``hdrconv.io.read_21496``
    - ``hdrconv.convert.gainmap_to_hdr``
    - ``hdrconv.core.GainmapImage``
"""

__version__ = "0.1.0"

from . import convert, core, identify, io

__all__ = [
    "convert",
    "core",
    "identify",
    "io",
]
