"""
Composer and generator implementations for gain map based formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import numpy as np
from PIL import Image as PILImage

from ..models import Image, ImageContainer, ImageType, IntermediateRendering
from .composer_base import Composer
from .generator_base import Generator


def _normalise_array(values: np.ndarray) -> np.ndarray:
    if np.issubdtype(values.dtype, np.floating):
        return values.astype(np.float32)
    if np.issubdtype(values.dtype, np.integer):
        max_val = np.iinfo(values.dtype).max
        return values.astype(np.float32) / max_val
    raise TypeError(f"Unsupported dtype {values.dtype!r} for normalisation.")


def eotf_display_p3(image: np.ndarray) -> np.ndarray:
    linear_image = np.where(
        image <= 0.0031308, image / 12.92, np.power((image + 0.055) / 1.055, 2.4)
    )
    return linear_image


def oetf_inverse_709(image: np.ndarray) -> np.ndarray:
    linear_image = np.where(
        image <= 0.08145, image / 4.5, np.power((image + 0.099) / 1.099, 1 / 0.45)
    )
    return linear_image


def _resize_gain_map(content: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """
    Resize gain map array to match the target base image resolution.
    """
    pil_image = PILImage.fromarray(np.squeeze(content))
    resized = pil_image.resize(size, PILImage.BILINEAR)
    array = np.asarray(resized)
    if array.ndim == 2:
        array = array[..., np.newaxis]
    return array


def apply_gain_map(base_image: Image, gain_map: Image, headroom: float) -> np.ndarray:
    """
    Applies the HDR gain map to the base SDR image to reconstruct a linear HDR image.
    """
    resized_gain_map = _resize_gain_map(gain_map.content, (base_image.width, base_image.height))
    gain_map_norm = _normalise_array(resized_gain_map.squeeze())
    gain_map_linear = oetf_inverse_709(gain_map_norm)
    base_norm = _normalise_array(base_image.content)
    base_linear = eotf_display_p3(base_norm)
    gain_map_linear = gain_map_linear[..., np.newaxis]
    hdr_linear = base_linear * (1.0 + (headroom - 1.0) * gain_map_linear)
    return hdr_linear


@dataclass(slots=True)
class GainmapOptions:
    headroom: float = 6.0


class GainmapComposer(Composer):
    """
    Compose a linear HDR rendering from an SDR base layer and gain map.
    """

    def __init__(self, default_headroom: float = 6.0) -> None:
        self.default_headroom = default_headroom

    def compose(self, container: ImageContainer) -> IntermediateRendering:
        base = _find_image(container, ImageType.SDR)
        gain = _find_image(container, ImageType.GAINMAP)
        if gain is None:
            raise ValueError("Gain map composer requires a gain map image.")
        headroom = _resolve_headroom(container.metadata, self.default_headroom)
        hdr_linear = apply_gain_map(base, gain, headroom)
        return IntermediateRendering(hdr_linear)


class GainmapGenerator(Generator):
    """
    Placeholder generator for producing gain map containers from a rendering.
    """

    def generate(
        self, rendering: IntermediateRendering, options: dict[str, float] | None = None
    ) -> ImageContainer:
        raise NotImplementedError("Gain map generation is not implemented yet.")


def _find_image(container: ImageContainer, image_type: ImageType) -> Optional[Image]:
    for image in container.images:
        if image.image_type == image_type:
            return image
    return None


def _resolve_headroom(metadata: Mapping[str, object], default_headroom: float) -> float:
    """
    Attempt to find a headroom value in the metadata.
    """
    candidates = [
        metadata.get("HDRGainMapHeadroom"),
        metadata.get("hdrgainmap_headroom"),
        metadata.get("apple_headroom"),
    ]
    for value in candidates:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default_headroom


__all__ = [
    "GainmapComposer",
    "GainmapGenerator",
    "GainmapOptions",
    "apply_gain_map",
]
