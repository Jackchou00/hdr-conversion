"""ISO 21496-1 Gainmap conversion utilities.

This module provides functions for converting between ISO 21496-1 Gainmap
format and linear HDR representation.

The ISO 21496-1 standard defines a method for encoding HDR content using
a baseline (SDR) image plus a gainmap that encodes the HDR-to-SDR ratio
in log2 space.

Public APIs:
    - `gainmap_to_hdr`: Reconstruct HDR from gainmap
    - `hdr_to_gainmap`: Create gainmap from HDR

See Also:
    ISO/TS 21496-1: Adaptive gain map for HDR still image
"""

from __future__ import annotations

from typing import Optional
import warnings

from PIL import Image
import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour

from hdrconv.core import GainmapImage, GainmapMetadata, HDRImage
from hdrconv.convert.colorspace import convert_color_space


def gainmap_to_hdr(
    data: GainmapImage,
    baseline_color_space: str = "p3",
    alt_color_space: str = "p3",
    target_color_space: str = "bt2020",
) -> HDRImage:
    """Convert ISO 21496-1 Gainmap to linear HDR image.

    Applies the gainmap to the baseline image to reconstruct the alternate
    (HDR) representation using the ISO 21496-1 formula:

    - G' = (G^(1/gamma)) * (max - min) + min
    - L = 2^G'
    - HDR = L * (baseline + baseline_offset) - alternate_offset

    Args:
        data: GainmapImage dict containing baseline, gainmap, and metadata.
        baseline_color_space: Color space of baseline image.
            Options: 'bt709', 'p3', 'bt2020'. Default: 'p3'.
        alt_color_space: Color space of alternate/HDR image.
            Options: 'bt709', 'p3', 'bt2020'. Default: 'p3'.
        target_color_space: Target output color space.
            Options: 'bt709', 'p3', 'bt2020'. Default: 'bt2020'.

    Returns:
        HDRImage dict with the following keys:
        - ``data`` (np.ndarray): Linear HDR array, float32, shape (H, W, 3).
        - ``color_space`` (str): Target color space string.
        - ``transfer_function`` (str): Always 'linear'.
        - ``icc_profile`` (bytes | None): Always None.

    Note:
        The baseline image is assumed to be sRGB-encoded. The function
        automatically applies EOTF conversion to linear light before
        applying the gainmap formula.

    See Also:
        - `hdr_to_gainmap`: Inverse operation, create gainmap from HDR.
        - `convert_color_space`: For additional color space transformations.
    """
    baseline = data["baseline"].astype(np.float32) / 255.0  # Normalize to [0, 1]
    baseline = colour.eotf(baseline, function="sRGB")
    gainmap = data["gainmap"].astype(np.float32) / 255.0
    metadata = data["metadata"]

    use_base_colour_space = metadata["use_base_colour_space"]
    if not use_base_colour_space:
        baseline = convert_color_space(
            baseline,
            source_space=baseline_color_space,
            target_space=alt_color_space,
        )
    else:
        gainmap = convert_color_space(
            gainmap,
            source_space=alt_color_space,
            target_space=baseline_color_space,
        )

    # Resize gainmap to match baseline if needed
    h, w = baseline.shape[:2]
    if gainmap.shape[:2] != (h, w):
        # Use Pillow for resizing: convert float32 [0,1] -> uint8 [0,255] -> resize -> back to float32
        gainmap_uint8 = np.clip(gainmap * 255.0, 0, 255).astype(np.uint8)

        # Handle 2D grayscale and 3D RGB arrays
        if gainmap_uint8.ndim == 2:
            pil_image = Image.fromarray(gainmap_uint8, mode="L")
        else:
            pil_image = Image.fromarray(gainmap_uint8, mode="RGB")

        # Resize using bilinear interpolation (equivalent to cv2.INTER_LINEAR)
        pil_image_resized = pil_image.resize((w, h), Image.BILINEAR)

        # Convert back to float32 [0,1]
        gainmap = np.array(pil_image_resized, dtype=np.float32) / 255.0

    # Ensure gainmap is 3-channel for calculations
    if gainmap.ndim == 2:
        gainmap = gainmap[:, :, np.newaxis]
    if gainmap.shape[2] == 1:
        gainmap = np.repeat(gainmap, 3, axis=2)

    # Extract metadata (convert to arrays for broadcasting)
    gainmap_min = np.array(metadata["gainmap_min"], dtype=np.float32)
    gainmap_max = np.array(metadata["gainmap_max"], dtype=np.float32)
    gainmap_gamma = np.array(metadata["gainmap_gamma"], dtype=np.float32)
    baseline_offset = np.array(metadata["baseline_offset"], dtype=np.float32)
    alternate_offset = np.array(metadata["alternate_offset"], dtype=np.float32)

    gainmap = np.clip(gainmap, 0.0, 1.0)

    # Decode gainmap: apply gamma, scale, and offset
    gainmap_decoded = (gainmap ** (1 / gainmap_gamma)) * (
        gainmap_max - gainmap_min
    ) + gainmap_min

    # Convert to linear multiplier
    gainmap_linear = np.exp2(gainmap_decoded)

    # Reconstruct alternate (HDR) image
    hdr_linear = gainmap_linear * (baseline + baseline_offset) - alternate_offset

    # Color space conversion
    if not use_base_colour_space:
        hdr_linear = convert_color_space(
            hdr_linear, source_space=alt_color_space, target_space=target_color_space
        )
    else:
        hdr_linear = convert_color_space(
            hdr_linear,
            source_space=baseline_color_space,
            target_space=target_color_space,
        )

    hdr_linear = np.clip(hdr_linear, 0.0, None)

    return HDRImage(
        data=hdr_linear,
        color_space=target_color_space,
        transfer_function="linear",
        icc_profile=None,
    )


def hdr_to_gainmap(
    hdr: HDRImage,
    baseline: Optional[np.ndarray] = None,
    color_space: str = "bt709",
    icc_profile: Optional[bytes] = None,
    gamma: float = 1.0,
) -> GainmapImage:
    """Convert linear HDR image to ISO 21496-1 Gainmap format.

    Creates a gainmap by computing the log2 ratio between HDR and SDR images.
    If baseline is not provided, generates one by clipping HDR to [0, 1].

    Args:
        hdr: HDRImage dict with linear HDR data in any supported color space.
        baseline: Optional pre-computed baseline (SDR) image.
            If None, generated by clipping HDR to [0, 1].
            Expected format: float32, shape (H, W, 3), range [0, 1].
        color_space: Target color space for output.
            Options: 'bt709', 'p3', 'bt2020'. Default: 'bt709'.
        icc_profile: Optional ICC profile bytes to embed in output.
            Should match the specified color_space.
        gamma: Gainmap gamma parameter for encoding.
            Higher values compress highlights. Default: 1.0.

    Returns:
        GainmapImage dict containing:
        - ``baseline`` (np.ndarray): SDR image, uint8, shape (H, W, 3).
        - ``gainmap`` (np.ndarray): Gain map, uint8, shape (H, W, 3).
        - ``metadata`` (GainmapMetadata): Computed transformation parameters.
        - ``baseline_icc`` (bytes | None): Provided ICC profile.
        - ``gainmap_icc`` (bytes | None): Provided ICC profile.

    Note:
        Uses fixed offsets of 1/64 for both baseline and alternate to
        avoid division by zero in dark regions.

    See Also:
        - `gainmap_to_hdr`: Inverse operation, reconstruct HDR from gainmap.
        - `write_21496`: Write GainmapImage to ISO 21496-1 JPEG.
    """
    hdr_data = hdr["data"].astype(np.float32)

    # convert to target colour space
    hdr_data = convert_color_space(
        hdr_data, source_space=hdr["color_space"], target_space=color_space
    )

    hdr_data = np.clip(hdr_data, 0.0, None)

    # Generate baseline if not provided
    if baseline is None:
        baseline = hdr_data.copy()
        baseline = np.clip(baseline, 0.0, 1.0)

    # Compute alt headroom
    alt_headroom = np.log2(hdr_data.max() + 1e-6)

    # preset offset for both baseline and alternate = 1/64
    alt_offset = float(1 / 64)
    base_offset = float(1 / 64)

    ratio = (hdr_data + alt_offset) / (baseline + base_offset)
    ratio = np.clip(ratio, 1e-6, None)

    gainmap_log = np.log2(ratio)

    gainmap_min_val = np.min(gainmap_log, axis=(0, 1))
    gainmap_max_val = np.max(gainmap_log, axis=(0, 1))

    gainmap_norm = (gainmap_log - gainmap_min_val) / (gainmap_max_val - gainmap_min_val)
    gainmap_norm = np.clip(gainmap_norm, 0, 1)

    gainmap_norm = gainmap_norm**gamma

    gainmap_uint8 = (gainmap_norm * 255).astype(np.uint8)

    baseline = colour.eotf_inverse(baseline, function="sRGB")
    baseline_uint8 = (baseline * 255).astype(np.uint8)

    gainmap_min_val = tuple(gainmap_min_val.tolist())
    gainmap_max_val = tuple(gainmap_max_val.tolist())

    metadata = GainmapMetadata(
        minimum_version=0,
        writer_version=0,
        baseline_hdr_headroom=1.0,
        alternate_hdr_headroom=float(alt_headroom),
        is_multichannel=True,
        use_base_colour_space=True,
        gainmap_min=gainmap_min_val,
        gainmap_max=gainmap_max_val,
        gainmap_gamma=(gamma, gamma, gamma),
        baseline_offset=(base_offset, base_offset, base_offset),
        alternate_offset=(alt_offset, alt_offset, alt_offset),
    )

    return GainmapImage(
        baseline=baseline_uint8,
        gainmap=gainmap_uint8,
        metadata=metadata,
        baseline_icc=icc_profile,
        gainmap_icc=icc_profile,
    )
