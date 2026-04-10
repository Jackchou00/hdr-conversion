"""iOS HDR Screenshot to UltraHDR Conversion Example.

This example demonstrates how to:
1. Read an iOS HDR screenshot (HEIC format)
2. Write directly as UltraHDR (JPEG with gainmap) without intermediate HDR conversion

Requirements:
    - MP4Box (from GPAC package)
    - ffmpeg

Install on macOS:
    brew install gpac ffmpeg
"""

import argparse

from hdrconv.io import read_ios_hdr_screenshot, write_ultrahdr


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input iOS HDR screenshot")
    parser.add_argument("icc_path", help="Display P3 ICC")
    parser.add_argument("output_path", help="UltraHDR JPEG output")
    args = parser.parse_args()

    print(f"Reading iOS HDR screenshot: {args.input_path}")

    # Read iOS HDR screenshot as GainmapImage
    # The function auto-detects grid layout and original resolution from the file
    gainmap_image = read_ios_hdr_screenshot(args.input_path)

    print(f"  Main image shape: {gainmap_image['baseline'].shape}")
    print(f"  Gainmap shape: {gainmap_image['gainmap'].shape}")
    print(f"  Gainmap max: {gainmap_image['metadata']['gainmap_max']}")
    print(f"  Offset: {gainmap_image['metadata']['baseline_offset']}")

    # Load Display P3 ICC profile and embed it
    print(f"\nLoading Display P3 ICC profile: {args.icc_path}")
    with open(args.icc_path, "rb") as f:
        p3_icc = f.read()

    # Directly add ICC profile to the GainmapImage
    gainmap_image["baseline_icc"] = p3_icc
    gainmap_image["gainmap_icc"] = p3_icc

    # Write directly as UltraHDR JPEG (no HDR conversion needed)
    write_ultrahdr(gainmap_image, args.output_path)

    print(f"\n Written UltraHDR output: {args.output_path}")


if __name__ == "__main__":
    main()
