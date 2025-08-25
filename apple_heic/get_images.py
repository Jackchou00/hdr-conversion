"""
Extracts main image and gainmap from HEIC files shot by iPhone.

Modified from: https://github.com/finnschi/heic-shenanigans/blob/main/gain_map_extract.py

iPhone's Gainmap is an auxiliary image with 1/4 the resolution of the main image and a single channel.
"""

import pillow_heif
import numpy as np
from PIL import Image
from typing import Tuple, Optional

# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def read_base_and_gain_map(input_path: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Reads the base image and HDR gain map from a HEIC file and returns them as NumPy arrays.

    This function specifically looks for the auxiliary image identified by the URN
    'urn:com:apple:photo:2020:aux:hdrgainmap' as the gain map.

    Args:
        input_path (str): Path to the input HEIC image file.

    Returns:
        A tuple containing two elements (base_image, gain_map):
        - base_image (np.ndarray): NumPy array of the main image.
        - gain_map (np.ndarray | None): NumPy array of the HDR gain map.
    """
    try:
        heif_file = pillow_heif.read_heif(input_path, convert_hdr_to_8bit=False)
    except Exception as e:
        print(f"Error: Unable to read HEIC file '{input_path}': {e}")
        raise

    # Base Image
    base_image_pil = Image.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    base_image_np = np.array(base_image_pil)

    # Gain Map
    gain_map_np = None  # Default to None if not found

    # Check if 'aux' metadata exists and if our desired URN is one of its keys
    if "aux" in heif_file.info and HDR_GAIN_MAP_URN in heif_file.info["aux"]:
        gain_map_ids = heif_file.info["aux"][HDR_GAIN_MAP_URN]

        if gain_map_ids:
            try:
                # Take the first ID from the list
                gain_map_id = gain_map_ids[0]
                # Use the ID to get the auxiliary image object
                aux_image = heif_file.get_aux_image(gain_map_id)

                # Create a PIL.Image object from the raw data, mode, size, and stride
                gain_map_pil = Image.frombytes(
                    aux_image.mode,
                    aux_image.size,
                    aux_image.data,
                    "raw",
                    aux_image.mode,
                    aux_image.stride,
                )
                gain_map_np = np.array(gain_map_pil)
            except Exception as e:
                # Handle rare cases where the ID exists but the image data cannot be extracted
                print(f"Warning: Unable to extract gain map with ID {gain_map_id}: {e}")

    return base_image_np, gain_map_np


# --- Usage Example ---
if __name__ == "__main__":
    file_path = "apple_heic/IMG_6850.HEIC"  # your HEIC file path

    base_image, gain_map = read_base_and_gain_map(file_path)

    if base_image is not None:
        print("\nBase Image:")
        print(f"  - Type: {type(base_image)}")
        print(f"  - Shape: {base_image.shape}")
        print(f"  - Dtype: {base_image.dtype}")

        np.save("base_image.npy", base_image)

    if gain_map is not None:
        print("\nGain Map:")
        print(f"  - Type: {type(gain_map)}")
        print(f"  - Shape: {gain_map.shape}")
        print(f"  - Dtype: {gain_map.dtype}")

        np.save("gain_map.npy", gain_map)
    else:
        print("\nHDR gain map not found in this file.")
