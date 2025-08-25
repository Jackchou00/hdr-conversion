# import numpy as np
# import colour

from img_output import save_np_array_to_avif
from utils import pq_eotf_inverse
from apple_heic.color_conversion import apply_gain_map
from apple_heic.get_images import read_base_and_gain_map
from apple_heic.headroom import get_headroom


file_path = ".HEIC"

(base_image, gain_map) = read_base_and_gain_map(file_path)
headroom = get_headroom(file_path)

if base_image is None or gain_map is None or headroom is None:
    raise ValueError("Failed to retrieve necessary image data or metadata.")

hdr_image_linear = apply_gain_map(base_image, gain_map, headroom)

hdr_image_linear = hdr_image_linear * 203.0
hdr_image_pq = pq_eotf_inverse(hdr_image_linear)

save_np_array_to_avif(hdr_image_pq, "output.avif")
