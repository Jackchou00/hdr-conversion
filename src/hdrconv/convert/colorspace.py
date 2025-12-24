from __future__ import annotations

import warnings

import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour


def convert_color_space(
    image: np.ndarray, source_space: str, target_space: str, clip: bool = False
) -> np.ndarray:
    """Convert image between color spaces (requires linear input).

    Args:
        image: Linear RGB image data, float32, shape (H, W, 3)
        source_space: Source color space ('bt709', 'p3', 'bt2020')
        target_space: Target color space ('bt709', 'p3', 'bt2020')
        clip: Whether to clip output to [0, inf)]

    Returns:
        Converted image in target color space

    Example:
        >>> # Convert from Display P3 to BT.2020
        >>> rgb_bt2020 = convert_color_space(rgb_p3, 'p3', 'bt2020')
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
