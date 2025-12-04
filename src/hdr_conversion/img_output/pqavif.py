from imagecodecs import avif_encode
import numpy as np


def save_np_array_to_avif(
    np_array, output_path, color_primaries=12, transfer_characteristics=16
):
    """
    Convert a numpy array to a HEIF/AVIF image and save it to the specified output path.

    :param np_array: The input numpy array representing the image, range [0, 1], dtype=float32.
    :param output_path: The path where the output image will be saved.
    :param color_primaries: Specifies the color primaries for the image.
                            - 1 for BT.709, 9 for BT.2020, 12 for P3-D65
    :param transfer_characteristics: Specifies the transfer characteristics for the image.
                                     - 1 for BT.709, 8 for Linear, 16 for PQ, 18 for HLG
    """
    # Normalize the numpy array to the range [0, 1] and then scale it to [0, 65535]
    np_array = np.clip(np_array, 0, 1)
    # scale to [0, 1023]
    np_array = np_array * 1023
    np_array = np_array.astype(np.uint16)

    avif_bytes: bytes = avif_encode(
        np_array,
        level=90,
        speed=8,
        bitspersample=10,
        primaries=color_primaries,
        transfer=transfer_characteristics,
        numthreads=-1,
    )

    # Write the AVIF bytes to the output file
    with open(output_path, "wb") as f:
        f.write(avif_bytes)


if __name__ == "__main__":
    # Example usage
    # Assuming hdr is defined and is a numpy array representing the HDR image
    hdr = np.random.rand(100, 100, 3)  # Replace with actual HDR image data
    output_path = "output.avif"

    save_np_array_to_avif(
        hdr, output_path, color_primaries=12, transfer_characteristics=16
    )
