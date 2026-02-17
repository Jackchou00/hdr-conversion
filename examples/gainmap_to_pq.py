"""
Example: ISO 21496-1 Gainmap to PQ AVIF conversion

This example demonstrates the new direct API for converting
between HDR formats with full control over each step.
"""

import hdrconv.io as io
import hdrconv.convert as convert

import colour
import numpy as np

# Step 1: Read ISO 21496-1 Gainmap JPEG
print("Reading ISO 21496-1 file...")
gainmap_data = io.read_21496("images/iso21496.jpg")

print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
print(f"  Metadata: {gainmap_data['metadata']}")

"""
'use_base_colour_space': False
base_colour_space: display-p3, alternate_colour_space: bt2020
manually convert baseline image to bt2020 space

gainmap_to_hdr requires baseline to be in linear light space.
"""

baseline_image = (
    gainmap_data["baseline"].astype(np.float32) / 255.0
)  # Normalize to [0, 1]
baseline = colour.eotf(baseline_image, function="sRGB")  # Convert to linear light
baseline_bt2020 = colour.RGB_to_RGB(
    baseline, input_colourspace="Display P3", output_colourspace="ITU-R BT.2020"
)
gainmap_data["baseline"] = (baseline_bt2020 * 255.0).astype(np.uint8)

# Step 2: Convert Gainmap to linear HDR
print("\nConverting Gainmap to linear HDR...")
hdr = convert.gainmap_to_hdr(gainmap_data)

print(f"  HDR shape: {hdr['data'].shape}")
print(f"  HDR dtype: {hdr['data'].dtype}")
print(f"  Value range: [{hdr['data'].min():.4f}, {hdr['data'].max():.4f}]")

# Step 3: Apply PQ transfer function
print("\nApplying PQ transfer function...")
pq_encoded = colour.eotf_inverse(hdr["data"] * 203.0, function="ITU-R BT.2100 PQ")

print(f"  PQ range: [{pq_encoded.min():.4f}, {pq_encoded.max():.4f}]")

# Step 4: Write as ISO 22028-5 PQ AVIF
print("\nWriting PQ AVIF...")
pq_data = {
    "data": pq_encoded,
    "color_space": "bt2020",
    "transfer_function": "pq",
    "icc_profile": None,
}
io.write_22028_pq(pq_data, "output_from_21496.avif")

print("✓ Conversion complete!")
print("\nOutput: output_from_21496.avif")
