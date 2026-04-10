"""
Example: Linear HDR to ISO 21496-1 Gainmap conversion

Demonstrates converting from pure HDR format to Gainmap format.
"""

import argparse

import hdrconv.io as io
import hdrconv.convert as convert

import numpy as np

def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input linear HDR .npy")
    parser.add_argument("icc_path", help="Baseline ICC")
    parser.add_argument("output_path", help="ISO 21496-1 JPEG output")
    args = parser.parse_args()

    # Step 1: Read Linear HDR
    p3_lin_rgb = np.load(args.input_path) / 203.0  # Normalize to [0, 1] range
    # Rotate CW 90.
    p3_lin_rgb = np.rot90(p3_lin_rgb, k=-1)

    hdr = {
        "data": p3_lin_rgb,
        "color_space": "p3",
        "transfer_function": "linear",
    }

    print(f"  Linear range: [{p3_lin_rgb.min():.4f}, {p3_lin_rgb.max():.4f}]")

    # Read the ICC profile.
    with open(args.icc_path, "rb") as f:
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
    io.write_21496(gainmap_data, args.output_path)

    print("✓ Conversion complete!")
    print(f"\nOutput: {args.output_path}")


if __name__ == "__main__":
    main()
