"""
Example: PQ AVIF to ISO 21496-1 Gainmap conversion

Demonstrates converting from pure HDR format to Gainmap format.
"""

import hdrconv.io as io
import hdrconv.convert as convert

import colour

# Step 1: Read PQ AVIF
print("Reading PQ AVIF file...")
pq_data = io.read_22028_pq("images/iso22028.avif")

print(f"  PQ data shape: {pq_data['data'].shape}")
print(f"  Color space: {pq_data['color_space']}")
print(f"  Transfer: {pq_data['transfer_function']}")

# Step 2: Convert PQ to linear HDR
print("\nConverting PQ to linear...")
linear_hdr = colour.eotf(pq_data["data"], function="ITU-R BT.2100 PQ") / 203.0

hdr = {
    "data": linear_hdr,
    "color_space": "bt2020",
    "transfer_function": "linear",
}

print(f"  Linear range: [{linear_hdr.min():.4f}, {linear_hdr.max():.4f}]")

# Step 3: Convert HDR to Gainmap format

# read a bt.2020 icc profile
with open("icc/ITU-R_BT2020-beta.icc", "rb") as f:
    bt2020_icc = f.read()

print("\nGenerating Gainmap...")
gainmap_data = convert.hdr_to_gainmap(
    hdr,
    baseline=None,  # Auto-generate SDR baseline
    icc_profile=bt2020_icc,
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
