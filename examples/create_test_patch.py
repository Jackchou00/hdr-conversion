import colour
import numpy as np

import hdrconv.io as io
import hdrconv.convert as convert
from hdrconv.core import HDRImage

# baseline: pure blue in sRGB
# alternate: pure red in Display P3


with open("icc/sRGB2014.icc", "rb") as f:
    p3_icc = f.read()

with open("icc/Display P3.icc", "rb") as f:
    bt2020_icc = f.read()

image_width = 512
image_height = 512

baseline_image = np.zeros((image_height, image_width, 3), dtype=np.float32)
baseline_image[:, :, 2] = 1.0
alternate_image = np.zeros((image_height, image_width, 3), dtype=np.float32)
alternate_image[:, :, 0] = 1.0

# convert baseline to bt.2020
baseline_image_bt2020 = colour.RGB_to_RGB(
    baseline_image, input_colourspace="sRGB", output_colourspace="Display P3"
)

hdr_image: HDRImage = {
    "data": alternate_image,
}

gainmap_full_image = convert.hdr_to_gainmap(hdr_image, baseline_image_bt2020)

gainmap_full_image["metadata"]["use_base_colour_space"] = False

print("Gainmap metadata:")
for key, value in gainmap_full_image["metadata"].items():
    print(f"{key}: {value}")

baseline_image = colour.eotf_inverse(baseline_image, function="sRGB")
baseline_image = (baseline_image * 255.0).astype(np.uint8)
gainmap_full_image["baseline"] = baseline_image
gainmap_full_image["baseline_icc"] = p3_icc
gainmap_full_image["gainmap_icc"] = bt2020_icc

io.write_21496(gainmap_full_image, "test_gainmap.jpg")
