"""
Example: Direct metadata manipulation

Demonstrates low-level control over Gainmap metadata for research.
"""

import hdrconv.io as io

# Read existing Gainmap image
data = io.read_21496("images/iso21496.jpg")

io.write_21496(data, "output_original_metadata.jpg")
print("✓ Original file written")

# Access and modify metadata directly
metadata = data["metadata"]

print("Original metadata:")
print(f"  Gainmap min: {metadata['gainmap_min']}")
print(f"  Gainmap max: {metadata['gainmap_max']}")
print(f"  Gainmap gamma: {metadata['gainmap_gamma']}")
print(f"  Baseline headroom: {metadata['baseline_hdr_headroom']}")
print(f"  Alternate headroom: {metadata['alternate_hdr_headroom']}")

# Modify metadata for experimentation
metadata["gainmap_gamma"] = (1.5, 1.5, 1.5)  # Adjust gamma
metadata["alternate_hdr_headroom"] = 10.0  # Increase headroom

# Write with modified metadata
io.write_21496(data, "output_modified_metadata.jpg")

print("\n✓ File written with modified metadata")
