"""
Combine SDR image and Gainmap to reconstruct a single HDR image.

Reference: https://developer.apple.com/documentation/appkit/applying-apple-hdr-effect-to-your-photos
"""

from PIL import Image
import numpy as np


def eotf_display_p3(image: np.ndarray) -> np.ndarray:
    linear_image = np.where(
        image <= 0.0031308, image / 12.92, np.power((image + 0.055) / 1.055, 2.4)
    )
    return linear_image


def oetf_inverse_709(image: np.ndarray) -> np.ndarray:
    linear_image = np.where(
        image <= 0.08145, image / 4.5, np.power((image + 0.099) / 1.099, 1 / 0.45)
    )
    return linear_image


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
    gain_map_linear = oetf_inverse_709(gain_map_norm)

    # Step 3: Linearize the SDR image.
    base_image_norm = base_image.astype(np.float32) / 255.0
    # base_image_linear = colour.eotf(base_image_norm, "sRGB")
    base_image_linear = eotf_display_p3(base_image_norm)

    # hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)
    hdr_image_linear = base_image_linear * (
        1.0 + (headroom - 1.0) * gain_map_linear[..., np.newaxis]
    )

    return hdr_image_linear


# --- Usage Example ---
if __name__ == "__main__":
    base_image = np.load("base_image.npy")
    gain_map = np.load("gain_map.npy")
    headroom_value = 6.902454  # Example headroom value

    hdr_img = apply_gain_map(base_image, gain_map, headroom_value)
    print("HDR image reconstructed successfully.")
    print("HDR image shape:", hdr_img.shape)
    print("HDR image data type:", hdr_img.dtype)
    print(f"HDR image max value: {hdr_img.max()}")
    print(f"HDR image min value: {hdr_img.min()}")

    np.save("hdr_image.npy", hdr_img)
