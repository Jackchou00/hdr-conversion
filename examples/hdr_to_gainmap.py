"""
Example: Linear HDR to ISO 21496-1 Gainmap conversion

Demonstrates converting from pure HDR format to Gainmap format.
"""

import hdrconv.io as io
import hdrconv.convert as convert

import numpy as np

# Step 1: Read Linear HDR
p3_lin_rgb = np.load("rgb_linear.npy") / 203.0  # Normalize to [0, 1] range
# rotate CW 90
p3_lin_rgb = np.rot90(p3_lin_rgb, k=-1)

hdr = {
    "data": p3_lin_rgb,
    "color_space": "p3",
    "transfer_function": "linear",
}

print(f"  Linear range: [{p3_lin_rgb.min():.4f}, {p3_lin_rgb.max():.4f}]")

# read an icc profile
with open("baseline.icc", "rb") as f:
    icc = f.read()

print("\nGenerating Gainmap...")
gainmap_data = convert.hdr_to_gainmap(
    hdr,
    baseline=None,  # Auto-generate SDR baseline
    icc_profile=icc,
    gamma=1.0,
)

print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
print(f"  Headroom: {gainmap_data['metadata']['alternate_hdr_headroom']:.2f}")

# Step 4: Write as ISO 21496-1
print("\nWriting ISO 21496-1 file...")
io.write_21496(gainmap_data, "output_gainmap.jpg")

print("✓ Conversion complete!")
print("\nOutput: output_gainmap.jpg")
