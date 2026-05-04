"""
Example: Apple HEIC to ISO 21496-1 Gainmap JPEG conversion

Converts Apple's HDR HEIC (Display P3) into ISO 21496-1 gainmap JPEG,
keeping the baseline in P3 and embedding the Display P3 ICC profile.
"""

import argparse

import hdrconv.io as io
import hdrconv.convert as convert
import hdrconv.identify as identify


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input Apple HEIC")
    parser.add_argument("icc_path", help="Display P3 ICC")
    parser.add_argument("iso_output_path", help="ISO 21496-1 JPEG output")
    parser.add_argument("uhdr_output_path", help="UltraHDR JPEG output")
    args = parser.parse_args()

    # Step 0: Identify input file
    print("Identifying input file...")
    ident = identify.has_gain_map(args.input_path)
    print(f"  Has gain map: {ident}")

    # Step 1: Read Apple HEIC
    print("Reading Apple HEIC file...")
    heic_data = io.read_apple_heic(args.input_path)

    print(f"  Base image shape: {heic_data['base'].shape}")
    print(f"  Gainmap shape: {heic_data['gainmap'].shape}")
    print(f"  Headroom: {heic_data['headroom']:.4f}")

    # Step 2: Convert to linear HDR (Display P3)
    print("\nApplying Apple gain map...")
    hdr = convert.apple_heic_to_hdr(heic_data)

    print(f"  HDR shape: {hdr['data'].shape}")

    # Step 3: Load Display P3 ICC profile
    print("\nLoading Display P3 ICC profile...")
    with open(args.icc_path, "rb") as f:
        p3_icc = f.read()

    # Step 4: Convert HDR to ISO 21496-1 Gainmap (baseline stays in P3)
    print("\nGenerating Gainmap (P3 baseline)...")
    gainmap_data = convert.hdr_to_gainmap(
        hdr,
        baseline=None,  # Auto-generate SDR baseline
        icc_profile=p3_icc,
        gamma=1.0,
    )

    print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
    print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
    print(f"  Headroom: {gainmap_data['metadata']['alternate_hdr_headroom']:.2f}")

    # Step 5: Write ISO 21496-1 JPEG with quality control
    print("\nWriting ISO 21496-1 file...")
    io.write_21496(gainmap_data, args.iso_output_path)

    # Step 6: Write UltraHDR JPEG
    print("Writing UltraHDR file...")
    io.write_ultrahdr(gainmap_data, args.uhdr_output_path)


if __name__ == "__main__":
    main()
