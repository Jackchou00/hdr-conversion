from hdrconv import save_np_array_to_avif, apply_gain_map, read_base_and_gain_map, get_headroom
import colour


file_path = ".HEIC"

(base_image, gain_map) = read_base_and_gain_map(file_path)
headroom = get_headroom(file_path)

if base_image is None or gain_map is None or headroom is None:
    raise ValueError("Failed to retrieve necessary image data or metadata.")

hdr_image_linear = apply_gain_map(base_image, gain_map, headroom)

hdr_image_linear = hdr_image_linear * 203.0
hdr_image_pq = colour.eotf_inverse(hdr_image_linear, function="ITU-R BT.2100 PQ")

save_np_array_to_avif(hdr_image_pq, "output.avif")
