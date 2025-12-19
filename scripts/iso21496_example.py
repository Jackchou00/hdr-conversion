from PIL import Image
import rich

from hdr_conversion.iso21496.io import decode_iso21496, encode_iso21496

iso21496_example_image_path = "images/iso21496.jpg"
iso21496_image_obj = decode_iso21496(iso21496_example_image_path)

baseline_image = Image.fromarray(iso21496_image_obj.baseline_image).save("images/baseline.jpg")
gainmap_image = Image.fromarray(iso21496_image_obj.gainmap_image).save("images/gainmap.jpg")

metadata = iso21496_image_obj.gainmap_metadata
rich.print(metadata)

encode_iso21496(iso21496_image_obj, "images/iso21496_reencoded.jpg")
