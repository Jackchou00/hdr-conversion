import pillow_heif
import numpy as np
from PIL import Image

"""
Note: pillow_heif no longer supports AVIF after version 0.22.0 since pillow already supports AVIF natively.

Need to transfer the AVIF saving functionality to use pillow's native support for AVIF.
"""


# Save HDR image
pillow_heif.options.QUALITY = -1


def save_np_array_to_avif(
    np_array, output_path, color_primaries=12, transfer_characteristics=16
):
    """
    Convert a numpy array to a HEIF/AVIF image and save it to the specified output path.

    :param np_array: The input numpy array representing the image.
    :param output_path: The path where the output image will be saved.
    :param color_primaries: Specifies the color primaries for the image.
                            - 1 for BT.709, 9 for BT.2020, 12 for P3-D65
    :param transfer_characteristics: Specifies the transfer characteristics for the image.
                                     - 1 for BT.709, 8 for Linear, 16 for PQ, 18 for HLG
    """
    # Normalize the numpy array to the range [0, 1] and then scale it to [0, 65535]
    np_array = np.clip(np_array, 0, 1)
    np_array = np_array * 65535
    np_array = np_array.astype(np.uint16)

    # Create a HEIF image from the numpy array
    img = pillow_heif.from_bytes(
        mode="RGB;16",
        size=(np_array.shape[1], np_array.shape[0]),
        data=np_array.tobytes(),
    )

    # Define the save parameters
    kwargs = {
        "format": "AVIF",
        "color_primaries": color_primaries,
        "transfer_characteristics": transfer_characteristics,
    }

    # Save the image to the specified output path
    img.save(output_path, **kwargs)


if __name__ == "__main__":
    # Example usage
    # Assuming hdr is defined and is a numpy array representing the HDR image
    hdr = np.random.rand(100, 100, 3)  # Replace with actual HDR image data
    output_path = "pq_avif_to_gainmap/output.avif"

    save_np_array_to_avif(
        hdr, output_path, color_primaries=12, transfer_characteristics=16
    )
