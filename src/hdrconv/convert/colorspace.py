"""Color space conversion utilities.

This module provides functions for converting between different RGB color
spaces used in HDR imaging workflows.

Supported color spaces:
    - 'bt709': ITU-R BT.709 (sRGB primaries)
    - 'p3': DCI-P3 / Display P3
    - 'bt2020': ITU-R BT.2020 (wide gamut HDR)

Public APIs:
    - `convert_color_space`: Transform between color spaces

Note:
    All conversions require linear light input. Apply EOTF first if
    working with gamma-encoded data.
"""

from __future__ import annotations

import warnings

import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour


def convert_color_space(
    image: np.ndarray, source_space: str, target_space: str, clip: bool = False
) -> np.ndarray:
    """Convert image between color spaces.

    Transforms RGB values from one color space to another using chromatic
    adaptation and matrix transformations. Input must be in linear light.

    Args:
        image: Linear RGB image data, float32, shape (H, W, 3).
            Values should be in linear light (not gamma-encoded).
        source_space: Source color space identifier.
            Options: 'bt709' (Rec. 709), 'p3' (Display P3), 'bt2020' (Rec. 2020).
        target_space: Target color space identifier.
            Options: 'bt709', 'p3', 'bt2020'.
        clip: Whether to clip output to [0, inf). Default: False.
            Enable when negative values from gamut mapping are undesirable.

    Returns:
        Converted image in target color space, same shape as input.
        Values remain in linear light.

    Note:
        If source_space equals target_space, returns input unchanged.
        Uses colour-science library for accurate color transformations.

    See Also:
        - `apply_pq`: Apply PQ transfer function after color space conversion.
        - `gainmap_to_hdr`: Includes color space conversion in HDR reconstruction.
    """
    space_map = {"bt709": "ITU-R BT.709", "p3": "DCI-P3", "bt2020": "ITU-R BT.2020"}

    if source_space == target_space:
        return image

    source_name = space_map.get(source_space, source_space)
    target_name = space_map.get(target_space, target_space)

    target_image = colour.RGB_to_RGB(
        image, input_colourspace=source_name, output_colourspace=target_name
    )

    if clip:
        target_image = np.clip(target_image, 0.0, None)
    return target_image
