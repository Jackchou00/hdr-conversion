"""ISO 21496-1 Gainmap conversion utilities.

This module provides functions for converting between ISO 21496-1 Gainmap
format and linear HDR representation.

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
from hdrconv.icc import linearize_array_with_icc


def _as_triplet(values: object, field_name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.size == 1:
        return np.repeat(arr, 3)
    if arr.size == 3:
        return arr
    raise ValueError(
        f"Invalid metadata field '{field_name}': expected 1 or 3 values, got {arr.size}."
    )


def _resize_gainmap_array(gainmap: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    gainmap_uint8 = np.clip(gainmap * 255.0, 0, 255).astype(np.uint8)

    if gainmap_uint8.ndim == 2:
        pil_image = Image.fromarray(gainmap_uint8, mode="L")
    elif gainmap_uint8.ndim == 3:
        channel_count = gainmap_uint8.shape[2]
        if channel_count == 1:
            pil_image = Image.fromarray(gainmap_uint8[:, :, 0], mode="L")
        elif channel_count == 3:
            pil_image = Image.fromarray(gainmap_uint8, mode="RGB")
        elif channel_count == 4:
            pil_image = Image.fromarray(gainmap_uint8, mode="RGBA")
        else:
            pil_image = Image.fromarray(gainmap_uint8[:, :, 0], mode="L")
    else:
        raise ValueError(
            f"Invalid gainmap shape for resize: expected 2D or 3D array, got {gainmap_uint8.shape}."
        )

    pil_image_resized = pil_image.resize(size, Image.BILINEAR)
    gainmap_resized = np.array(pil_image_resized, dtype=np.float32) / 255.0

    if gainmap_resized.ndim == 2:
        gainmap_resized = gainmap_resized[:, :, np.newaxis]
    elif gainmap_resized.ndim == 3 and gainmap_resized.shape[2] == 4:
        gainmap_resized = gainmap_resized[:, :, :3]

    return gainmap_resized


def gainmap_to_hdr(
    data: GainmapImage,
) -> HDRImage:
    """Convert ISO 21496-1 Gainmap to linear HDR image.

    Applies the gainmap to the baseline image to reconstruct the alternate
    (HDR) representation using the ISO 21496-1 formula:

    - G' = (G^(1/gamma)) * (max - min) + min
    - L = 2^G'
    - HDR = L * (baseline + baseline_offset) - alternate_offset

    Args:
        data: GainmapImage dict containing baseline, gainmap, and metadata.
    Returns:
        HDRImage dict with the following keys:
        - ``data`` (np.ndarray): Linear HDR array, float32, shape (H, W, 3).
        - ``transfer_function`` (str): Always 'linear'.

    See Also:
        - `hdr_to_gainmap`: Inverse operation, create gainmap from HDR.
    """

    # Linearize baseline
    baseline = data["baseline"].astype(np.float32) / 255.0  # Normalize to [0, 1]
    icc_source = data.get("baseline_icc")
    linear_baseline = None
    if icc_source:
        try:
            linear_baseline = linearize_array_with_icc(data["baseline_icc"], baseline)
        except Exception as e:
            warnings.warn(e)
    if linear_baseline is None:
        linear_baseline = colour.eotf(baseline, function="sRGB")

    gainmap = data["gainmap"].astype(np.float32) / 255.0
    metadata = data["metadata"]

    # Resize gainmap to match baseline if needed
    h, w = baseline.shape[:2]
    if gainmap.shape[:2] != (h, w):
        gainmap = _resize_gainmap_array(gainmap, (w, h))

    # Ensure gainmap is 3-channel for calculations
    if gainmap.ndim == 2:
        gainmap = gainmap[:, :, np.newaxis]
    if gainmap.shape[2] == 1:
        gainmap = np.repeat(gainmap, 3, axis=2)

    # TODO: Move metadata channel normalization to a shared helper across I/O paths.
    gainmap_min = _as_triplet(metadata["gainmap_min"], "gainmap_min")
    gainmap_max = _as_triplet(metadata["gainmap_max"], "gainmap_max")
    gainmap_gamma = _as_triplet(metadata["gainmap_gamma"], "gainmap_gamma")
    baseline_offset = _as_triplet(metadata["baseline_offset"], "baseline_offset")
    alternate_offset = _as_triplet(metadata["alternate_offset"], "alternate_offset")

    gainmap = np.clip(gainmap, 0.0, 1.0)

    # Decode gainmap: apply gamma, scale, and offset
    gainmap_decoded = (gainmap ** (1 / gainmap_gamma)) * (
        gainmap_max - gainmap_min
    ) + gainmap_min

    # Convert to linear multiplier
    gainmap_linear = np.exp2(gainmap_decoded)

    # Reconstruct alternate (HDR) image
    hdr_linear = gainmap_linear * (linear_baseline + baseline_offset) - alternate_offset

    hdr_linear = np.clip(hdr_linear, 0.0, None)

    return HDRImage(
        data=hdr_linear,
        transfer_function="linear",
        icc_profile=None,
    )


def hdr_to_gainmap(
    hdr: HDRImage,
    baseline: Optional[np.ndarray] = None,
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

    # Generate baseline if not provided
    if baseline is None:
        baseline = hdr_data.copy()
        baseline = np.clip(baseline, 0.0, 1.0)

    # Compute alt headroom
    alt_headroom = np.log2(hdr_data.max() + 1e-6)
    # temporarily set a minimum headroom to avoid extremely small values that can't be encoded
    if alt_headroom <= 0.01:
        alt_headroom = 0.01

    # preset offset for both baseline and alternate = 1/64
    alt_offset = float(1 / 64)
    base_offset = float(1 / 64)

    ratio = (hdr_data + alt_offset) / (baseline + base_offset)
    ratio = np.clip(ratio, 1e-6, None)

    gainmap_log = np.log2(ratio)

    gainmap_min_val = np.min(gainmap_log, axis=(0, 1))
    gainmap_max_val = np.max(gainmap_log, axis=(0, 1))

    gainmap_norm = np.zeros_like(gainmap_log)
    for i in range(3):
        diff = gainmap_max_val[i] - gainmap_min_val[i]
        if diff == 0:
            gainmap_norm[:, :, i] = 0.0
        else:
            gainmap_norm[:, :, i] = (gainmap_log[:, :, i] - gainmap_min_val[i]) / diff
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
        baseline_hdr_headroom=0.0,
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
