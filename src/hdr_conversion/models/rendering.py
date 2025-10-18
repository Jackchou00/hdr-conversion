"""
Intermediate HDR representation shared across format interpreters.
"""

from __future__ import annotations

import numpy as np

from .colorspaces import BT2020_LINEAR
from .image import Image, ImageType


class IntermediateRendering(Image):
    """
    Canonical linear HDR image used to bridge between disparate formats.
    """

    def __init__(self, content: np.ndarray) -> None:
        super().__init__(content=content, colorspace=BT2020_LINEAR, image_type=ImageType.HDR)


__all__ = ["IntermediateRendering"]
