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

from typing import Literal, Optional
import warnings

import cv2
import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour

from hdrconv.core import GainmapImage, GainmapMetadata, HDRImage
from hdrconv.icc import linearize_array_with_icc, convert_array_with_icc_matrix

GainmapResizeMethod = Literal["shepard", "lanczos4", "linear", "nearest"]


def _as_triplet(values: object, field_name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.size == 1:
        return np.repeat(arr, 3)
    if arr.size == 3:
        return arr
    raise ValueError(
        f"Invalid metadata field '{field_name}': expected 1 or 3 values, got {arr.size}."
    )


def _normalize_sample_array(
    arr: np.ndarray,
    bit_depth: int | None,
    field_name: str,
) -> np.ndarray:
    arr = np.asarray(arr)

    if np.issubdtype(arr.dtype, np.floating):
        return np.clip(arr.astype(np.float32), 0.0, 1.0)

    if bit_depth is None:
        raise ValueError(f"{field_name}_bit_depth is required for integer samples.")
    if bit_depth <= 0:
        raise ValueError(f"Invalid {field_name}_bit_depth: {bit_depth}.")

    sample_max = (1 << bit_depth) - 1
    return np.clip(arr.astype(np.float32) / float(sample_max), 0.0, 1.0)


def _prepare_gainmap_for_resize(gainmap: np.ndarray) -> np.ndarray:
    gainmap = np.asarray(gainmap, dtype=np.float32)

    if gainmap.ndim == 2:
        gainmap = gainmap[:, :, np.newaxis]
    elif gainmap.ndim != 3:
        raise ValueError(
            f"Invalid gainmap shape for resize: expected 2D or 3D array, got {gainmap.shape}."
        )

    return gainmap


def _resize_gainmap_shepard(gainmap: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Resize a gainmap using libultrahdr-style 4-neighbour Shepard IDW."""
    gainmap = _prepare_gainmap_for_resize(gainmap)
    src_h, src_w = gainmap.shape[:2]
    dst_w, dst_h = size

    if dst_w <= 0 or dst_h <= 0:
        raise ValueError(f"Invalid resize target size: {size}.")

    scale_x = dst_w / src_w
    scale_y = dst_h / src_h

    x_map = np.arange(dst_w, dtype=np.float32) / np.float32(scale_x)
    x_lower = np.floor(x_map).astype(np.intp)
    x_upper = np.minimum(x_lower + 1, src_w - 1)
    x_lower = np.minimum(x_lower, src_w - 1)

    dx_lower = x_map - x_lower.astype(np.float32)
    dx_upper = x_map - x_upper.astype(np.float32)

    y_map = (np.arange(dst_h) / scale_y).astype(np.float32)
    y_lower_all = np.minimum(np.floor(y_map).astype(np.intp), src_h - 1)
    y_upper_all = np.minimum(y_lower_all + 1, src_h - 1)

    dy_lower_all = (y_map - y_lower_all.astype(np.float32))[:, np.newaxis]
    dy_upper_all = (y_map - y_upper_all.astype(np.float32))[:, np.newaxis]

    # Channel-first layout keeps the per-channel arithmetic on contiguous 2D planes.
    planes = np.ascontiguousarray(np.moveaxis(gainmap, 2, 0))
    cols_lower = np.take(planes, x_lower, axis=2)
    cols_upper = np.take(planes, x_upper, axis=2)

    out = np.empty((gainmap.shape[2], dst_h, dst_w), dtype=np.float32)

    # Process destination rows in blocks: the fully vectorized form
    # materializes ~16 destination-size planes at once, which peaks at
    # gigabytes for 48MP upscales. ~1M elements per plane bounds the
    # temporaries while keeping the inner math vectorized.
    block_rows = max(1, (1 << 20) // max(dst_w, 1))
    for y0 in range(0, dst_h, block_rows):
        y1 = min(y0 + block_rows, dst_h)
        y_lower = y_lower_all[y0:y1]
        y_upper = y_upper_all[y0:y1]
        dy_lower = dy_lower_all[y0:y1]
        dy_upper = dy_upper_all[y0:y1]

        d1 = np.hypot(dx_lower, dy_lower)
        d2 = np.hypot(dx_lower, dy_upper)
        d3 = np.hypot(dx_upper, dy_lower)
        d4 = np.hypot(dx_upper, dy_upper)

        w1 = np.divide(1.0, d1, out=np.zeros_like(d1), where=d1 != 0.0)
        w2 = np.divide(1.0, d2, out=np.zeros_like(d2), where=d2 != 0.0)
        w3 = np.divide(1.0, d3, out=np.zeros_like(d3), where=d3 != 0.0)
        w4 = np.divide(1.0, d4, out=np.zeros_like(d4), where=d4 != 0.0)
        total = w1 + w2 + w3 + w4
        # d_i == 0 exactly when both fraction components are 0
        # (hypot(x, y) >= max(|x|, |y|)).
        exact_any = ((dy_lower == 0.0) | (dy_upper == 0.0)) & (
            (dx_lower == 0.0) | (dx_upper == 0.0)
        )
        total = np.where(exact_any, 1.0, total)

        v1 = np.take(cols_lower, y_lower, axis=1)
        v2 = np.take(cols_lower, y_upper, axis=1)
        v3 = np.take(cols_upper, y_lower, axis=1)
        v4 = np.take(cols_upper, y_upper, axis=1)

        resized = v1 * w1
        resized += v2 * w2
        resized += v3 * w3
        resized += v4 * w4
        resized /= total

        for dx, dy, v in (
            (dx_lower, dy_lower, v1),
            (dx_lower, dy_upper, v2),
            (dx_upper, dy_lower, v3),
            (dx_upper, dy_upper, v4),
        ):
            rows = np.flatnonzero(dy == 0.0)
            cols = np.flatnonzero(dx == 0.0)
            if rows.size and cols.size:
                resized[:, rows[:, np.newaxis], cols] = v[:, rows[:, np.newaxis], cols]

        out[:, y0:y1] = resized

    return np.ascontiguousarray(np.moveaxis(out, 0, 2))


def _resize_gainmap_cv2(
    gainmap: np.ndarray, size: tuple[int, int], interpolation: int
) -> np.ndarray:
    gainmap = _prepare_gainmap_for_resize(gainmap)

    # Anti-aliasing prefilter from next-work/imresize_aa.py, intentionally disabled for now.
    # h, w = gainmap.shape[:2]
    # w2, h2 = size
    # scale_x = w2 / w
    # scale_y = h2 / h
    # if scale_x < 1.0 or scale_y < 1.0:
    #     sigma = 0.3 / min(scale_x, scale_y)
    #     ksize = int(6 * sigma + 1)
    #     if ksize % 2 == 0:
    #         ksize += 1
    #     gainmap = cv2.GaussianBlur(gainmap, (ksize, ksize), sigmaX=sigma)

    resized = cv2.resize(gainmap, dsize=size, interpolation=interpolation)
    if resized.ndim == 2:
        resized = resized[:, :, np.newaxis]

    return resized.astype(np.float32, copy=False)


def _resize_gainmap_array(
    gainmap: np.ndarray,
    size: tuple[int, int],
    method: GainmapResizeMethod = "shepard",
) -> np.ndarray:
    if method == "shepard":
        return _resize_gainmap_shepard(gainmap, size)
    if method == "lanczos4":
        return _resize_gainmap_cv2(gainmap, size, cv2.INTER_LANCZOS4)
    if method == "linear":
        return _resize_gainmap_cv2(gainmap, size, cv2.INTER_LINEAR)
    if method == "nearest":
        return _resize_gainmap_cv2(gainmap, size, cv2.INTER_NEAREST)

    raise ValueError(
        "Invalid gainmap resize method: "
        f"{method!r}. Expected one of 'shepard', 'lanczos4', 'linear', or 'nearest'."
    )


def gainmap_to_hdr(
    data: GainmapImage,
    gainmap_resize_method: GainmapResizeMethod = "shepard",
) -> HDRImage:
    """Convert ISO 21496-1 Gainmap to linear HDR image.

    Applies the gainmap to the baseline image to reconstruct the alternate
    (HDR) representation using the ISO 21496-1 formula:

    - G' = (G^(1/gamma)) * (max - min) + min
    - L = 2^G'
    - HDR = L * (baseline + baseline_offset) - alternate_offset

    Args:
        data: GainmapImage dict containing baseline, gainmap, and metadata.
        gainmap_resize_method: Method used when gainmap and baseline dimensions differ.
            ``"shepard"`` matches libultrahdr's 4-neighbour inverse-distance weighting.
    Returns:
        HDRImage dict with the following keys:
        - ``data`` (np.ndarray): Linear HDR array, float32, shape (H, W, 3).
        - ``transfer_function`` (str): Always 'linear'.
        - ``icc_profile`` (bytes | None): ICC profile describing the working
          color space of the reconstruction: ``baseline_icc`` when
          ``use_base_colour_space`` is True, otherwise ``gainmap_icc`` when the
          baseline was converted to the alternate space (falling back to
          ``baseline_icc`` if the conversion was skipped or failed).

    See Also:
        - `hdr_to_gainmap`: Inverse operation, create gainmap from HDR.
    """

    # Linearize baseline
    baseline = _normalize_sample_array(
        data["baseline"], data.get("baseline_bit_depth"), "baseline"
    )
    icc_source = data.get("baseline_icc")
    linear_baseline = None
    if icc_source:
        try:
            linear_baseline = linearize_array_with_icc(data["baseline_icc"], baseline)
        except Exception as e:
            warnings.warn(
                "Failed to linearize baseline with its ICC profile "
                f"({type(e).__name__}: {e}); falling back to sRGB EOTF.",
                stacklevel=2,
            )
    if linear_baseline is None:
        linear_baseline = colour.eotf(baseline, function="sRGB").astype(np.float32)

    gainmap = _normalize_sample_array(
        data["gainmap"], data.get("gainmap_bit_depth"), "gainmap"
    )
    metadata = data["metadata"]

    # Resize gainmap to match baseline if needed
    h, w = baseline.shape[:2]
    if gainmap.shape[:2] != (h, w):
        gainmap = _resize_gainmap_array(gainmap, (w, h), gainmap_resize_method)

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

    # if use_base_colour_space is False, convert baseline to alternate space
    output_icc = data.get("baseline_icc")
    if not data["metadata"]["use_base_colour_space"]:
        linear_baseline_alt = None
        if data["baseline_icc"] is not None and data["gainmap_icc"] is not None:
            try:
                linear_baseline_alt = convert_array_with_icc_matrix(
                    source_icc=data["baseline_icc"],
                    target_icc=data["gainmap_icc"],
                    img_array=linear_baseline,
                )
                output_icc = data["gainmap_icc"]
            except Exception as e:
                warnings.warn(
                    "Failed to convert baseline to alternate color space "
                    f"({type(e).__name__}: {e}); keeping baseline color space.",
                    stacklevel=2,
                )
        if linear_baseline_alt is None:
            linear_baseline_alt = linear_baseline
        linear_baseline = linear_baseline_alt

    # Reconstruct alternate (HDR) image
    hdr_linear = gainmap_linear * (linear_baseline + baseline_offset) - alternate_offset
    hdr_linear = np.clip(hdr_linear, 0.0, None).astype(np.float32, copy=False)

    return HDRImage(
        data=hdr_linear,
        transfer_function="linear",
        icc_profile=output_icc,
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
            ``transfer_function`` must be ``'linear'``.
        baseline: Optional pre-computed baseline (SDR) image in LINEAR light —
            do not pass sRGB/gamma-encoded data (the sRGB encoding is applied
            internally when storing the baseline).
            If None, generated by clipping HDR to [0, 1].
            Expected format: float32, shape (H, W, 3), range [0, 1].
        icc_profile: Optional ICC profile bytes to embed in output.
            Should describe the color space of ``hdr['data']``. Defaults to
            ``hdr['icc_profile']`` when omitted.
        gamma: Gainmap gamma parameter for encoding.
            Higher values compress highlights. Default: 1.0.

    Raises:
        ValueError: If ``hdr['transfer_function']`` is not ``'linear'``.

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
    if hdr["transfer_function"] != "linear":
        raise ValueError(
            "hdr_to_gainmap requires linear HDR data, but got "
            f"transfer_function={hdr['transfer_function']!r}. Linearize the data "
            "first (apply the matching EOTF) before calling hdr_to_gainmap."
        )

    if icc_profile is None:
        icc_profile = hdr.get("icc_profile")

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

    gainmap_uint8 = np.round(gainmap_norm * 255).astype(np.uint8)

    baseline = colour.eotf_inverse(baseline, function="sRGB")
    baseline_uint8 = np.round(baseline * 255).astype(np.uint8)

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
        baseline_bit_depth=8,
        gainmap_bit_depth=8,
    )
