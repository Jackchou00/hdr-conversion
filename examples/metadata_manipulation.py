"""
Example: Direct metadata manipulation

Demonstrates low-level control over Gainmap metadata for research.
"""

import hdrconv.io as io

# Read existing Gainmap image
data = io.read_21496("images/iso21496.jpg")

# save icc profile
with open("icc/baseline.icc", "wb") as f:
    f.write(data["baseline_icc"])
with open("icc/gainmap.icc", "wb") as f:
    f.write(data["gainmap_icc"])

io.write_21496(data, "output_original_metadata.jpg")
print("✓ Original file written")

# Access and modify metadata directly
metadata = data["metadata"]

print("Original metadata:")
print(f"  Baseline headroom: {metadata['baseline_hdr_headroom']}")
print(f"  Alternate headroom: {metadata['alternate_hdr_headroom']}")

# Modify metadata for experimentation
metadata["baseline_hdr_headroom"] = 1.0
metadata["alternate_hdr_headroom"] = 10.0  # Increase headroom

# Write with modified metadata
io.write_21496(data, "output_modified_metadata.jpg")

print("\n✓ File written with modified metadata")
