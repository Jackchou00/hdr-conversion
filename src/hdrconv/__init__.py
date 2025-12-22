"""
HDR Conversion Library

A Python library for converting between HDR image formats including:
- ISO 21496-1 Gainmap
- ISO 22028-5 PQ AVIF
- Apple HEIC HDR

Modules:
    convert: Core conversion functions between HDR formats
    io: I/O functions for reading and writing HDR files
    core: Data structures and type definitions

Example:
    >>> import hdrconv.io as io
    >>> import hdrconv.convert as convert
    >>>
    >>> # Read ISO 21496-1 Gainmap
    >>> gainmap_data = io.read_21496("image.jpg")
    >>>
    >>> # Convert to linear HDR
    >>> hdr = convert.gainmap_to_hdr(gainmap_data)
    >>>
    >>> # Apply PQ and write as AVIF
    >>> pq_encoded = convert.apply_pq(hdr['data'])
    >>> io.write_22028_pq({'data': pq_encoded, ...}, "output.avif")
"""

__version__ = "0.1.0a1"

# Import submodules for convenience
from . import convert
from . import io
from . import core

# Import core data structures
from .core import (
    GainmapMetadata,
    GainmapImage,
    HDRImage,
    PQImage,
    AppleHeicData,
)

__all__ = [
    # Modules
    "convert",
    "io",
    "core",
    # Data structures
    "GainmapMetadata",
    "GainmapImage",
    "HDRImage",
    "PQImage",
    "AppleHeicData",
]
