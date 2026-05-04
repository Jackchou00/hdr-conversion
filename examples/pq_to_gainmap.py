"""
Example: PQ AVIF to ISO 21496-1 Gainmap conversion

Demonstrates converting from pure HDR format to Gainmap format.
"""

import argparse

import hdrconv.io as io
import hdrconv.convert as convert

import colour


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input PQ AVIF")
    parser.add_argument("icc_path", help="BT.2020 ICC")
    parser.add_argument("output_path", help="ISO 21496-1 JPEG output")
    args = parser.parse_args()

    # Step 1: Read PQ AVIF
    print("Reading PQ AVIF file...")
    pq_data = io.read_22028_pq(args.input_path)

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
    with open(args.icc_path, "rb") as f:
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
    io.write_21496(gainmap_data, args.output_path)

    print("✓ Conversion complete!")
    print(f"\nOutput: {args.output_path}")


if __name__ == "__main__":
    main()
