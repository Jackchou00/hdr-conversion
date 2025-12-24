from __future__ import annotations

import numpy as np
from PIL import Image

from hdrconv.core import AppleHeicData, HDRImage


def apple_heic_to_hdr(data: AppleHeicData) -> HDRImage:
    """Convert Apple HEIC data to linear HDR.

    Uses Apple's gain map formula:
        hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

    Args:
        data: AppleHeicData dict with base, gainmap, and headroom

    Returns:
        HDRImage dict with linear HDR in Display P3 space

    Example:
        >>> heic = read_apple_heic('IMG_1234.HEIC')
        >>> hdr = apple_heic_to_hdr(heic)
        >>> linear_p3 = hdr['data']
    """

    def apply_gain_map(
        base_image: np.ndarray, gain_map: np.ndarray, headroom: float
    ) -> np.ndarray:
        if base_image is None or gain_map is None:
            raise ValueError("Both base_image and gain_map must be provided.")

        gain_map_resized = np.array(
            Image.fromarray(gain_map).resize(
                (base_image.shape[1], base_image.shape[0]), Image.BILINEAR
            )
        )

        gain_map_norm = gain_map_resized.astype(np.float32) / 255.0
        gain_map_linear = np.where(
            gain_map_norm <= 0.08145,
            gain_map_norm / 4.5,
            np.power((gain_map_norm + 0.099) / 1.099, 1 / 0.45),
        )
        gain_map_linear = np.clip(gain_map_linear, 0.0, 1.0)

        base_image_norm = base_image.astype(np.float32) / 255.0
        base_image_linear = np.where(
            base_image_norm <= 0.04045,
            base_image_norm / 12.92,
            np.power((base_image_norm + 0.055) / 1.055, 2.4),
        )
        base_image_linear = np.clip(base_image_linear, 0.0, 1.0)

        hdr_image_linear = base_image_linear * (
            1.0 + (headroom - 1.0) * gain_map_linear[..., np.newaxis]
        )
        hdr_image_linear = np.clip(hdr_image_linear, 0.0, None)
        return hdr_image_linear

    hdr_linear = apply_gain_map(data["base"], data["gainmap"], data["headroom"])

    return HDRImage(
        data=hdr_linear,
        color_space="p3",  # Apple uses Display P3
        transfer_function="linear",
        icc_profile=None,
    )
