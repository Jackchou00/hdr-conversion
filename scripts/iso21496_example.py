from PIL import Image
import rich
import numpy as np
import colour

from hdrconv.iso21496.io import decode_iso21496, encode_iso21496
from hdrconv.iso21496.calculate import to_alternate
from hdrconv.iso22028.io import encode_iso22028_2020_pq

iso21496_example_image_path = "images/iso21496.jpg"
iso21496_image_obj = decode_iso21496(iso21496_example_image_path)

baseline_image = Image.fromarray(iso21496_image_obj.baseline_image).save(
    "images/baseline.jpg"
)
gainmap_image = Image.fromarray(iso21496_image_obj.gainmap_image).save(
    "images/gainmap.jpg"
)

metadata = iso21496_image_obj.gainmap_metadata
rich.print(metadata)

encode_iso21496(iso21496_image_obj, "images/iso21496_reencoded.jpg")

# to alternate
# normalize images to [0, 1]
baseline_normalized = iso21496_image_obj.baseline_image.astype(np.float32) / 255.0
gainmap_normalized = iso21496_image_obj.gainmap_image.astype(np.float32) / 255.0

# convert baseline image to gainmap application colour space (will be automatically converted in future versions)
baseline_converted = colour.RGB_to_RGB(
    colour.eotf(baseline_normalized, "sRGB"),
    input_colourspace="DCI-P3",
    output_colourspace="ITU-R BT.2020",
)

# to alternate
alternate_image = to_alternate(
    baseline_converted, gainmap_normalized, iso21496_image_obj.gainmap_metadata
)

# save alternate image
alternate_image_pq = colour.eotf_inverse(alternate_image * 203, "ITU-R BT.2100 PQ")
alternate_image_pq_encoded = encode_iso22028_2020_pq(alternate_image_pq, "output.avif")
