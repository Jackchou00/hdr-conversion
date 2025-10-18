"""
Core image primitives shared across the conversion pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

import numpy as np
from colour import RGB_Colourspace


class ImageType(str, Enum):
    """Logical role that an image plays inside an HDR container."""

    SDR = "sdr"
    HDR = "hdr"
    GAINMAP = "gainmap"


@dataclass(slots=True)
class Image:
    """
    Represents a raster image tied to a specific colourspace.

    Args:
        content: Pixel data stored as either a 2D (single channel) or 3D array.
        coloursapce: Colourspace describing the pixel data.
        image_type: Semantic label describing the image role.
    """

    content: np.ndarray
    colorspace: RGB_Colourspace
    image_type: ImageType

    def __post_init__(self) -> None:
        if not isinstance(self.content, np.ndarray):
            raise TypeError("content must be a numpy ndarray.")
        if self.content.ndim not in (2, 3):
            raise ValueError("content must be 2D (mono) or 3D (multi-channel).")
        if not isinstance(self.colorspace, RGB_Colourspace):
            raise TypeError("colorspace must be an instance of RGB_Colourspace.")
        if not isinstance(self.image_type, ImageType):
            raise TypeError("image_type must be an instance of ImageType.")

    @property
    def shape(self) -> Tuple[int, ...]:
        return self.content.shape

    @property
    def height(self) -> int:
        return self.content.shape[0]

    @property
    def width(self) -> int:
        return self.content.shape[1]

    def as_float(self) -> np.ndarray:
        """
        Return the image data as float32 for downstream numeric processing.
        """
        if np.issubdtype(self.content.dtype, np.floating):
            return self.content.astype(np.float32, copy=False)
        return self.content.astype(np.float32) / np.iinfo(self.content.dtype).max

    def __repr__(self) -> str:
        colorspace_name = getattr(self.colorspace, "name", "Unknown")
        return (
            f"Image(type={self.image_type.value!r}, "
            f"shape={self.shape}, "
            f"colorspace={colorspace_name})"
        )


__all__ = ["Image", "ImageType"]
