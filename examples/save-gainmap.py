"""
Example: save ISO 21496-1 baseline and gainmap
"""

import argparse

import hdrconv.io as io
from hdrconv.io import build_icc_segments, encode_jpeg, insert_segments
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("input_path", help="Input ISO 21496-1")
    args = parser.parse_args()

    # Step 1: Read ISO 21496-1 Gainmap JPEG
    print("Reading ISO 21496-1 file...")
    gainmap_data = io.read_21496(args.input_path)

    print(
        f"  Baseline shape: {gainmap_data['baseline'].shape}, type: {gainmap_data['baseline'].dtype}"
    )
    print(
        f"  Gainmap shape: {gainmap_data['gainmap'].shape}, type: {gainmap_data['gainmap'].dtype}"
    )
    print(f"  Metadata: {gainmap_data['metadata']}")

    # normaize baseline and gainmap to [0, 1] range
    baseline = gainmap_data["baseline"] / 2 ** gainmap_data["baseline_bit_depth"]
    gainmap = gainmap_data["gainmap"] / 2 ** gainmap_data["gainmap_bit_depth"]

    # save jpeg
    print("Saving baseline and gainmap as JPEG...")

    baseline_jpeg = insert_segments(
        encode_jpeg(np.round(baseline * 255).astype(np.uint8)),
        build_icc_segments(gainmap_data["baseline_icc"]),
    )
    gainmap_jpeg = encode_jpeg(np.round(gainmap * 255).astype(np.uint8))

    with open("baseline.jpg", "wb") as f:
        f.write(baseline_jpeg)
    with open("gainmap.jpg", "wb") as f:
        f.write(gainmap_jpeg)


if __name__ == "__main__":
    main()
