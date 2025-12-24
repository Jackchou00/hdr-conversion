"""Apple HEIC HDR conversion utilities.

This module provides functions for converting Apple's proprietary HEIC
HDR format (with gain map) to standard linear HDR representation.

Apple's HDR format uses a single-channel gain map with the formula:
    hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

Public APIs:
    - `apple_heic_to_hdr`: Convert AppleHeicData to HDRImage

See Also:
    Apple Developer Documentation:
    https://developer.apple.com/documentation/appkit/applying-apple-hdr-effect-to-your-photos
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from hdrconv.core import AppleHeicData, HDRImage


def apple_heic_to_hdr(data: AppleHeicData) -> HDRImage:
    """Convert Apple HEIC gain map data to linear HDR.

        Applies Apple's proprietary gain map formula to reconstruct the HDR image
        from the SDR base and single-channel gain map.

        The reconstruction formula is:
            hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

        Where all values are in linear light space.

        Args:
            data: AppleHeicData dict containing:
                - `base`: SDR image, uint8, shape (H, W, 3), Display P3.
                - `gainmap`: Gain map, uint8, shape (H, W, 1).
                - `headroom`: Peak luminance multiplier.

        Returns:
            HDRImage dict with the following keys:
            - ``data`` (np.ndarray): Linear HDR array, float32, shape (H, W, 3).
            - ``color_space`` (str): 'p3' (Display P3, Apple's default).
            - ``transfer_function`` (str): 'linear'.
            - ``icc_profile`` (bytes | None): None.

        Note:
            The gain map is upscaled from 1/4 resolution using bilinear interpolation.
            Both base image (sRGB transfer) and gain map (Rec. 709 transfer) are
            linearized before applying the formula.

        See Also:
            - `read_apple_heic`: Read AppleHeicData from HEIC file.
            - `convert_color_space`: Convert output to BT.2020 if needed.
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
