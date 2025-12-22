from typing import Optional
import numpy as np
import cv2
import colour
from PIL import Image
from hdrconv.core import GainmapImage, HDRImage, AppleHeicData, GainmapMetadata


def gainmap_to_hdr(data: GainmapImage, target_color_space: str = "bt2020") -> HDRImage:
    """
    Convert Gainmap image to linear HDR using ISO 21496-1 formula.

    Applies the gainmap to baseline to reconstruct the alternate (HDR) image.

    Formula:
        G' = (G ** gamma) * (max - min) + min
        L = 2 ** G'
        HDR = L * (baseline + baseline_offset) - alternate_offset

    Args:
        data: GainmapImage dict with baseline, gainmap, and metadata
        target_color_space: Target color space ('bt709', 'p3', 'bt2020')

    Returns:
        HDRImage dict with linear HDR data

    Example:
        >>> gainmap_data = read_21496('image.jpg')
        >>> hdr = gainmap_to_hdr(gainmap_data, target_color_space='bt2020')
        >>> linear_rgb = hdr['data']  # Linear light, float32
    """
    baseline = data["baseline"].astype(np.float32) / 255.0  # Normalize to [0, 1]
    gainmap = data["gainmap"].astype(np.float32) / 255.0
    metadata = data["metadata"]

    # Resize gainmap to match baseline if needed
    h, w = baseline.shape[:2]
    if gainmap.shape[:2] != (h, w):
        gainmap = cv2.resize(gainmap, (w, h), interpolation=cv2.INTER_LINEAR)

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

    # Apply ISO 21496-1 reconstruction formula
    gainmap = np.clip(gainmap, 0.0, 1.0)

    # Decode gainmap: apply gamma, scale, and offset
    gainmap_decoded = (gainmap**gainmap_gamma) * (
        gainmap_max - gainmap_min
    ) + gainmap_min

    # Convert to linear multiplier
    gainmap_linear = np.exp2(gainmap_decoded)

    # Reconstruct alternate (HDR) image
    hdr_linear = gainmap_linear * (baseline + baseline_offset) - alternate_offset

    # Color space conversion
    # Note: Baseline is typically sRGB or P3, need to convert to target
    # For now, assume baseline is already linearized
    # TODO: Proper color space conversion based on baseline_icc

    return HDRImage(
        data=hdr_linear,
        color_space=target_color_space,
        transfer_function="linear",
        icc_profile=None,
    )


def hdr_to_gainmap(
    hdr: HDRImage,
    baseline: Optional[np.ndarray] = None,
    gamma: float = 1.0,
) -> GainmapImage:
    """
    Convert linear HDR to Gainmap format.

    Creates a gainmap by computing the ratio between HDR and SDR images.
    If baseline is not provided, generates one using tone mapping.

    Args:
        hdr: HDRImage dict with linear HDR data
        baseline: Optional pre-computed baseline (SDR) image, uint8 (H, W, 3)
        target_headroom: Target HDR headroom in stops (log2)
        gamma: Gainmap gamma parameter

    Returns:
        GainmapImage dict ready for writing
    """
    hdr_data = hdr["data"].astype(np.float32)

    # Generate baseline if not provided (simple tone mapping)
    if baseline is None:
        # Simple Reinhard tone mapping
        hdr_normalized = hdr_data / (1.0 + hdr_data)
        baseline = np.clip(hdr_normalized * 255, 0, 255).astype(np.uint8)

    # Normalize baseline for calculations
    baseline_norm = baseline.astype(np.float32) / 255.0

    # Compute alt headroom
    alt_headroom = np.log2(hdr_data.max() + 1e-6)

    # Compute gainmap from ratio
    # Avoid division by zero
    epsilon = 1e-6
    ratio = (hdr_data + epsilon) / (baseline_norm + epsilon)

    # Convert to log2 space
    gainmap_log = np.log2(np.clip(ratio, epsilon, 1000))

    # Determine gainmap range based on data
    gainmap_min_val = float(np.percentile(gainmap_log, 1))
    gainmap_max_val = float(np.percentile(gainmap_log, 99))

    # Normalize gainmap to [0, 1]
    gainmap_norm = (gainmap_log - gainmap_min_val) / (
        gainmap_max_val - gainmap_min_val + epsilon
    )
    gainmap_norm = np.clip(gainmap_norm, 0, 1)

    # Apply inverse gamma
    if gamma != 1.0:
        gainmap_norm = gainmap_norm ** (1.0 / gamma)

    # Convert to uint8
    gainmap_uint8 = (gainmap_norm * 255).astype(np.uint8)

    # Create metadata
    metadata = GainmapMetadata(
        minimum_version=0,
        writer_version=1,
        baseline_hdr_headroom=1.0,
        alternate_hdr_headroom=float(alt_headroom),
        is_multichannel=True,
        use_base_colour_space=False,
        gainmap_min=(gainmap_min_val, gainmap_min_val, gainmap_min_val),
        gainmap_max=(gainmap_max_val, gainmap_max_val, gainmap_max_val),
        gainmap_gamma=(gamma, gamma, gamma),
        baseline_offset=(0.0, 0.0, 0.0),
        alternate_offset=(0.0, 0.0, 0.0),
    )

    return GainmapImage(
        baseline=baseline,
        gainmap=gainmap_uint8,
        metadata=metadata,
        baseline_icc=None,
        gainmap_icc=None,
    )


def apple_heic_to_hdr(data: AppleHeicData) -> HDRImage:
    """
    Convert Apple HEIC data to linear HDR.

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
        """
        Applies the HDR gain map to the base SDR image to reconstruct the HDR image.

        Args:
            base_image (np.ndarray): The base SDR image as a NumPy array.
            gain_map (np.ndarray): The HDR gain map as a NumPy array.
            headroom (float): The headroom factor indicating the maximum gain.

        Returns:
            np.ndarray: The reconstructed HDR image.
        """
        if base_image is None or gain_map is None:
            raise ValueError("Both base_image and gain_map must be provided.")

        # Step 1: Resize the gainmap to match the base image's resolution.
        gain_map_resized = np.array(
            Image.fromarray(gain_map).resize(
                (base_image.shape[1], base_image.shape[0]), Image.BILINEAR
            )
        )

        # Step 2: Linearize the gainmap.
        # The gain map is typically a single-channel image with values in [0, 255].
        # We need to convert it to a linear scale [0, 1] for proper multiplication.
        gain_map_norm = gain_map_resized.astype(np.float32) / 255.0
        # gain_map_linear = colour.oetf_inverse(gain_map_norm, "ITU-R BT.709")
        gain_map_linear = np.where(
            gain_map_norm <= 0.08145,
            gain_map_norm / 4.5,
            np.power((gain_map_norm + 0.099) / 1.099, 1 / 0.45),
        )

        # Step 3: Linearize the SDR image.
        base_image_norm = base_image.astype(np.float32) / 255.0
        # base_image_linear = colour.eotf(base_image_norm, "sRGB")
        base_image_linear = np.where(
            base_image_norm <= 0.04045,
            base_image_norm / 12.92,
            np.power((base_image_norm + 0.055) / 1.055, 2.4),
        )

        # hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)
        hdr_image_linear = base_image_linear * (
            1.0 + (headroom - 1.0) * gain_map_linear[..., np.newaxis]
        )

        return hdr_image_linear

    hdr_linear = apply_gain_map(data["base"], data["gainmap"], data["headroom"])

    # Estimate max luminance
    max_luminance = float(np.percentile(hdr_linear, 99.9) * 10000)

    return HDRImage(
        data=hdr_linear,
        color_space="p3",  # Apple uses Display P3
        transfer_function="linear",
        max_luminance=max_luminance,
        icc_profile=None,
    )


def convert_color_space(
    image: np.ndarray, source_space: str, target_space: str
) -> np.ndarray:
    """
    Convert image between color spaces (requires linear input).

    Args:
        image: Linear RGB image data, float32, shape (H, W, 3)
        source_space: Source color space ('bt709', 'p3', 'bt2020')
        target_space: Target color space ('bt709', 'p3', 'bt2020')

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

    return colour.RGB_to_RGB(
        image, input_colourspace=source_name, output_colourspace=target_name
    )


def apply_pq(linear_rgb: np.ndarray) -> np.ndarray:
    """
    Apply PQ (Perceptual Quantizer) transfer function.

    Args:
        linear_rgb: Linear RGB data, float32, shape (H, W, 3)
        max_nits: Maximum luminance in nits for normalization

    Returns:
        PQ-encoded data, range [0, 1]

    Example:
        >>> pq_encoded = apply_pq(linear_hdr, max_nits=1000)
    """
    # Normalize to reference white (203 nits in PQ)
    pq_encoded = colour.models.eotf_inverse_BT2100_PQ(linear_rgb * 203.0)
    return pq_encoded


def inverse_pq(pq_encoded: np.ndarray) -> np.ndarray:
    """
    Apply inverse PQ to get linear RGB.

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
