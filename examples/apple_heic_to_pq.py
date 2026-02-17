"""
Example: Apple HEIC to PQ AVIF conversion

Demonstrates reading Apple's HDR format and converting to standard PQ AVIF.
"""

import hdrconv.io as io
import hdrconv.identify as identify
import hdrconv.convert as convert

import colour
import numpy as np

# Step 0: Identify input file
print("Identifying input file...")
ident = identify.has_gain_map("images/appleheic.HEIC")
print(f"  Has gain map: {ident}")

# Step 1: Read Apple HEIC
print("Reading Apple HEIC file...")
heic_data = io.read_apple_heic("images/appleheic.HEIC")

print(f"  Base image shape: {heic_data['base'].shape}")
print(f"  Gainmap shape: {heic_data['gainmap'].shape}")
print(f"  Headroom: {heic_data['headroom']:.4f}")

# Step 2: Convert to linear HDR
print("\nApplying Apple gain map...")
hdr = convert.apple_heic_to_hdr(heic_data)

print(f"  HDR shape: {hdr['data'].shape}")
print(f"  Color space: {hdr['color_space']}")  # Display P3

# Step 3: Convert color space from P3 to BT.2020
print("\nConverting P3 → BT.2020...")
hdr_bt2020 = colour.RGB_to_RGB(
    hdr["data"], input_colourspace="Display P3", output_colourspace="ITU-R BT.2020"
)

# Step 4: Apply PQ
print("\nApplying PQ transfer function...")
hdr_bt2020 = np.clip(hdr_bt2020, 0.0, np.inf)  # Ensure no negative values before PQ
pq_encoded = colour.eotf_inverse(hdr_bt2020 * 203.0, function="ITU-R BT.2100 PQ")
pq_encoded = np.clip(pq_encoded, 0.0, 1.0)  # Ensure values are in [0, 1]

# Step 5: Write as PQ AVIF
print("\nWriting PQ AVIF...")
pq_data = {
    "data": pq_encoded,
    "color_space": "bt2020",
    "transfer_function": "pq",
    "icc_profile": None,
}
io.write_22028_pq(pq_data, "output_from_heic.avif")

print("✓ Conversion complete!")
print("\nOutput: output_from_heic.avif")
