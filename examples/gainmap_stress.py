import argparse

from imagecodecs import avif_encode, AVIF
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Generate stress-test AVIF files.")
    parser.add_argument("alternate_output_path", help="Alternate AVIF output")
    parser.add_argument("baseline_output_path", help="Baseline AVIF output")
    args = parser.parse_args()

    # Generate alternate array.
    alternate = np.ones((1000, 1000, 3), dtype=np.float32) * 0.6
    # Convert to 12-bit uint16.
    alternate_uint16 = np.clip(alternate * 4095, 0, 4095).astype(np.uint16)
    # Encode to AVIF.
    avif_bytes = avif_encode(
        alternate_uint16,
        bitspersample=12,
        primaries=AVIF.COLOR_PRIMARIES.DCI_P3,
        transfer=AVIF.TRANSFER_CHARACTERISTICS.PQ,
        speed=6,
        level=AVIF.QUALITY.LOSSLESS,
        numthreads=8,
    )
    with open(args.alternate_output_path, "wb") as f:
        f.write(avif_bytes)

    # Generate baseline array.
    grid_size = 10
    cell_size = 100
    random_upper = 0.8
    random_lower = 0.2
    random_seed = 42
    np.random.seed(random_seed)
    baseline_grid = np.random.uniform(
        random_lower, random_upper, size=(grid_size, grid_size, 3)
    ).astype(np.float32)
    baseline = np.repeat(np.repeat(baseline_grid, cell_size, axis=0), cell_size, axis=1)
    # Convert to 12-bit uint16.
    baseline_uint16 = np.clip(baseline * 4095, 0, 4095).astype(np.uint16)
    # Encode to AVIF.
    avif_bytes = avif_encode(
        baseline_uint16,
        bitspersample=12,
        primaries=AVIF.COLOR_PRIMARIES.DCI_P3,
        transfer=AVIF.TRANSFER_CHARACTERISTICS.SRGB,
        speed=6,
        level=AVIF.QUALITY.LOSSLESS,
        numthreads=8,
    )
    with open(args.baseline_output_path, "wb") as f:
        f.write(avif_bytes)


if __name__ == "__main__":
    main()
