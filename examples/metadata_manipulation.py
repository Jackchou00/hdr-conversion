"""
Example: Direct metadata manipulation

Demonstrates low-level control over Gainmap metadata for research.
"""

import argparse

import hdrconv.io as io

def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input ISO 21496-1 JPEG")
    parser.add_argument("baseline_icc_output_path", help="Baseline ICC output")
    parser.add_argument("gainmap_icc_output_path", help="Gainmap ICC output")
    parser.add_argument("original_output_path", help="Original metadata JPEG output")
    parser.add_argument("modified_output_path", help="Modified metadata JPEG output")
    args = parser.parse_args()

    # Read existing Gainmap image
    data = io.read_21496(args.input_path)

    # Save ICC profiles.
    with open(args.baseline_icc_output_path, "wb") as f:
        f.write(data["baseline_icc"])
    with open(args.gainmap_icc_output_path, "wb") as f:
        f.write(data["gainmap_icc"])

    io.write_21496(data, args.original_output_path)
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
    io.write_21496(data, args.modified_output_path)

    print("\n✓ File written with modified metadata")


if __name__ == "__main__":
    main()
