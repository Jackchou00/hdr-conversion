import pillow_heif
import numpy as np
import colour


pillow_heif.register_avif_opener()


def extract_avif_image_array(avif_file_path):
    """
    Extracts the image array from an AVIF file.

    Args:
        avif_file_path (str): Path to the AVIF file.

    Returns:
        np.ndarray: The image array extracted from the AVIF file.
    """
    avif_file = pillow_heif.open_heif(avif_file_path, convert_hdr_to_8bit=False)
    image_array = np.asarray(avif_file)

    # Normalize to [0, 1]
    if image_array.dtype == np.uint16:
        image_array = image_array / 65535.0
    return image_array


def colour_convertion(pq_array):
    """
    Converts a PQ (Perceptual Quantizer) encoded image array to XYZ.

    Args:
        pq_array (np.ndarray): The PQ encoded image array.

    Returns:
        np.ndarray: The converted XYZ image array (Absolute Colorimetry).
    """
    # Convert PQ to linear RGB (absolute colorimetry)
    hdr_linear_rgb_image = colour.models.eotf_BT2100_PQ(pq_array)

    norm_linear_rgb_image = hdr_linear_rgb_image / 10000
    return norm_linear_rgb_image


def read_pq_avif(avif_file_path):
    """
    Reads an AVIF file and converts it to XYZ color space.

    Args:
        avif_file_path (str): Path to the AVIF file.

    Returns:
        np.ndarray: The XYZ image array.
    """
    pq_array = extract_avif_image_array(avif_file_path)
    xyz_image = colour_convertion(pq_array)
    return xyz_image
