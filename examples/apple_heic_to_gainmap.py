"""
Example: Apple HEIC to ISO 21496-1 Gainmap JPEG conversion

Converts Apple's HDR HEIC (Display P3) into ISO 21496-1 gainmap JPEG,
keeping the baseline in P3 and embedding the Display P3 ICC profile.
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

# Step 2: Convert to linear HDR (Display P3)
print("\nApplying Apple gain map...")
hdr = convert.apple_heic_to_hdr(heic_data)

print(f"  HDR shape: {hdr['data'].shape}")
print(f"  Color space: {hdr['color_space']}")  # Display P3

# Step 3: Load Display P3 ICC profile
print("\nLoading Display P3 ICC profile...")
with open("icc/Display P3.icc", "rb") as f:
    p3_icc = f.read()

# Step 4: Convert HDR to ISO 21496-1 Gainmap (baseline stays in P3)
print("\nGenerating Gainmap (P3 baseline)...")
gainmap_data = convert.hdr_to_gainmap(
    hdr,
    baseline=None,  # Auto-generate SDR baseline
    color_space="p3",
    icc_profile=p3_icc,
    gamma=1.0,
)

print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
print(f"  Headroom: {gainmap_data['metadata']['alternate_hdr_headroom']:.2f}")

# Step 5: Write ISO 21496-1 JPEG
print("\nWriting ISO 21496-1 file...")
io.write_21496(gainmap_data, "output_from_heic_gainmap_iso21496.jpg")

# Step 6: Write UltraHDR JPEG
print("Writing UltraHDR file...")
io.write_ultrahdr(gainmap_data, "output_from_heic_gainmap_uhdr.jpg")

print("✓ Conversion complete!")
print("\nOutputs:")
print("  - output_from_heic_gainmap_iso21496.jpg")
print("  - output_from_heic_gainmap_uhdr.jpg")
