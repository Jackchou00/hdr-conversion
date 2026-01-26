"""Transfer function utilities for HDR encoding.

This module provides functions for applying and inverting transfer functions
used in HDR content delivery, particularly PQ (Perceptual Quantizer).

Supported transfer functions:
    - PQ (SMPTE ST 2084): Used in HDR10, Dolby Vision
    - HLG (Hybrid Log-Gamma): Used in broadcast HDR

Public APIs:
    - `apply_pq`: Encode linear light to PQ
    - `inverse_pq`: Decode PQ to linear light

Note:
    PQ uses 203 nits as reference white (1.0 in linear scale).
    Values above 1.0 represent HDR highlights up to 10000 nits.
"""

from __future__ import annotations

import warnings

import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour


def apply_pq(linear_rgb: np.ndarray) -> np.ndarray:
    """Apply PQ (Perceptual Quantizer) transfer function.

    Encodes linear light RGB values to PQ (SMPTE ST 2084) transfer function
    as specified in ITU-R BT.2100 for HDR content.

    Args:
        linear_rgb: Linear RGB data, float32, shape (H, W, 3).
            Values should be normalized where 1.0 = 203 nits (reference white).
            Values above 1.0 represent HDR highlights up to ~49x (10000 nits).

    Returns:
        PQ-encoded data, float32, shape (H, W, 3), range [0, 1].
        Output is clipped to valid PQ range.

    Note:
        Uses 203 nits as reference white (PQ specification).
        Linear value of 1.0 maps to ~58% in PQ code values.

    See Also:
        - `inverse_pq`: Decode PQ back to linear light.
        - `write_22028_pq`: Write PQ-encoded data to AVIF file.
    """
    # Normalize to reference white (203 nits in PQ)
    pq_encoded = colour.models.eotf_inverse_BT2100_PQ(linear_rgb * 203.0)
    pq_encoded = np.clip(pq_encoded, 0.0, 1.0)
    return pq_encoded


def inverse_pq(pq_encoded: np.ndarray) -> np.ndarray:
    """Decode PQ-encoded values to linear light RGB.

    Applies the inverse PQ (SMPTE ST 2084) EOTF to convert PQ-encoded
    values back to linear light as specified in ITU-R BT.2100.

    Args:
        pq_encoded: PQ-encoded data, float32, shape (H, W, 3), range [0, 1].
            Values represent 0-10000 nits in PQ perceptual scale.

    Returns:
        Linear RGB data, float32, shape (H, W, 3).
        Normalized where 1.0 = 203 nits (reference white).
        HDR highlights may exceed 1.0 up to ~49x.

    Note:
        Uses 203 nits as reference white (PQ specification).
        PQ code value of ~0.58 maps to linear 1.0.

    See Also:
        - `apply_pq`: Encode linear light to PQ.
        - `read_22028_pq`: Read PQ-encoded AVIF file.
    """
    linear_normalized = colour.models.eotf_BT2100_PQ(pq_encoded)
    linear_rgb = linear_normalized / 203.0
    return linear_rgb
