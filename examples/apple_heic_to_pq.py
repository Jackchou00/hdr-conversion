"""
Example: Apple HEIC to PQ AVIF conversion

Demonstrates reading Apple's HDR format and converting to standard PQ AVIF.
"""

import hdrconv.io as io
import hdrconv.convert as convert
import hdrconv.identify as identify

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
hdr_bt2020 = convert.convert_color_space(
    hdr["data"], source_space="p3", target_space="bt2020", clip=True
)

# Step 4: Apply PQ
print("\nApplying PQ transfer function...")
pq_encoded = convert.apply_pq(hdr_bt2020)

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
