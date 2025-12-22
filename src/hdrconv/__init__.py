"""
HDR Conversion Library

A library for converting Apple HEIC HDR images to AVIF format.
"""

# Core functions for Apple HEIC processing
from .apple_heic.color_conversion import apply_gain_map
from .apple_heic.get_images import read_base_and_gain_map
from .apple_heic.headroom import get_headroom

# Core functions for image output
from .img_output.pqavif import save_np_array_to_avif

__all__ = [
    "apply_gain_map",
    "read_base_and_gain_map",
    "get_headroom",
    "save_np_array_to_avif"
]