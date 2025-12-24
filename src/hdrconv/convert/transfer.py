from __future__ import annotations

import warnings

import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    import colour


def apply_pq(linear_rgb: np.ndarray) -> np.ndarray:
    """Apply PQ (Perceptual Quantizer) transfer function.

    Args:
        linear_rgb: Linear RGB data, float32, shape (H, W, 3)

    Returns:
        PQ-encoded data, range [0, 1]

    Example:
        >>> pq_encoded = apply_pq(linear_hdr)
    """
    # Normalize to reference white (203 nits in PQ)
    pq_encoded = colour.models.eotf_inverse_BT2100_PQ(linear_rgb * 203.0)
    pq_encoded = np.clip(pq_encoded, 0.0, 1.0)
    return pq_encoded


def inverse_pq(pq_encoded: np.ndarray) -> np.ndarray:
    """Apply inverse PQ to get linear RGB.

    Args:
        pq_encoded: PQ-encoded data, range [0, 1]

    Returns:
        Linear RGB data

    Example:
        >>> linear_hdr = inverse_pq(pq_encoded)
    """
    linear_normalized = colour.models.eotf_BT2100_PQ(pq_encoded)
    linear_rgb = linear_normalized / 203.0
    return linear_rgb
