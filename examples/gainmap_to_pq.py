"""
Example: ISO 21496-1 Gainmap to PQ AVIF conversion

This example demonstrates the new direct API for converting
between HDR formats with full control over each step.
"""

import hdrconv.io as io
import hdrconv.convert as convert


# Step 1: Read ISO 21496-1 Gainmap JPEG
print("Reading ISO 21496-1 file...")
gainmap_data = io.read_21496("images/iso21496.jpg")

print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
print(f"  Metadata: {gainmap_data['metadata']}")

# save icc profiles for reference
if gainmap_data["baseline_icc"] is not None:
    with open("baseline.icc", "wb") as f:
        f.write(gainmap_data["baseline_icc"])

# Step 2: Convert Gainmap to linear HDR
print("\nConverting Gainmap to linear HDR...")
hdr = convert.gainmap_to_hdr(
    gainmap_data,
    baseline_color_space="p3",
    alt_color_space="bt2020",
    target_color_space="bt2020",
)

print(f"  HDR shape: {hdr['data'].shape}")
print(f"  HDR dtype: {hdr['data'].dtype}")
print(f"  Color space: {hdr['color_space']}")
print(f"  Value range: [{hdr['data'].min():.4f}, {hdr['data'].max():.4f}]")

# Step 3: Apply PQ transfer function
print("\nApplying PQ transfer function...")
pq_encoded = convert.apply_pq(hdr["data"])

print(f"  PQ range: [{pq_encoded.min():.4f}, {pq_encoded.max():.4f}]")

# Step 4: Write as ISO 22028-5 PQ AVIF
print("\nWriting PQ AVIF...")
pq_data = {
    "data": pq_encoded,
    "color_primaries": "bt2020",
    "transfer_characteristics": "pq",
    "bit_depth": 10,
}
io.write_22028_pq(pq_data, "output_from_21496.avif")

print("✓ Conversion complete!")
print("\nOutput: output_from_21496.avif")
