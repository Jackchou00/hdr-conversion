"""HDR format identification helpers.

This module provides functions for detecting HDR content and metadata
in various image formats.

Public APIs:
    - `has_gain_map`: Check if Apple HEIC file contains HDR gain map
"""

from .apple_heic import has_gain_map

__all__ = ["has_gain_map"]
