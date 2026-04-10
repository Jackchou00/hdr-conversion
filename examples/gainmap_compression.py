import argparse

import hdrconv.io as io


def main():
    parser = argparse.ArgumentParser(description="Re-encode a gainmap JPEG.")
    parser.add_argument("input_path", help="Input ISO 21496-1 JPEG")
    parser.add_argument("output_path", help="Compressed JPEG output")
    args = parser.parse_args()

    # Step 1: Read ISO 21496-1 Gainmap JPEG
    print("Reading ISO 21496-1 file...")
    gainmap_data = io.read_21496(args.input_path)

    print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
    print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
    print(f"  Metadata: {gainmap_data['metadata']}")

    io.write_21496(
        data=gainmap_data,
        filepath=args.output_path,
        gainmap_quality=60,
        baseline_quality=80,
    )


if __name__ == "__main__":
    main()
