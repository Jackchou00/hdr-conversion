from img_input import read_uhdr
from img_output import save_np_array_to_avif

import colour


def main():
    file = "sample_image_gainmap.jpg"

    # Read the UHDR image
    img = read_uhdr(file)

    img = colour.XYZ_to_RGB(img, colourspace="Display P3")
    img = colour.models.eotf_inverse_BT2100_PQ(img)

    # Save the image as AVIF
    save_np_array_to_avif(img, "output.avif")


if __name__ == "__main__":
    main()
