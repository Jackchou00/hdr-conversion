from imagecodecs import avif_encode, AVIF
import numpy as np


# generate alternate array
alternate = np.ones((1000, 1000, 3), dtype=np.float32) * 0.6
# convert to uint16 (but only 12 bit)
alternate_uint16 = np.clip(alternate * 4095, 0, 4095).astype(np.uint16)
# encode to AVIF
avif_bytes = avif_encode(
    alternate_uint16,
    bitspersample=12,
    primaries=AVIF.COLOR_PRIMARIES.DCI_P3,
    transfer=AVIF.TRANSFER_CHARACTERISTICS.PQ,
    speed=6,
    level=AVIF.QUALITY.LOSSLESS,
    numthreads=8,
)
with open("alternate.avif", "wb") as f:
    f.write(avif_bytes)

# generate baseline array
# baseline is a 10x10 grid with random colours, repeated to fill the 1000x1000 image
grid_size = 10
cell_size = 100
# random between 0.2-0.8
random_upper = 0.8
random_lower = 0.2
random_seed = 42
np.random.seed(random_seed)
baseline_grid = np.random.uniform(
    random_lower, random_upper, size=(grid_size, grid_size, 3)
).astype(np.float32)
baseline = np.repeat(np.repeat(baseline_grid, cell_size, axis=0), cell_size, axis=1)
# convert to uint16 (but only 12 bit)
baseline_uint16 = np.clip(baseline * 4095, 0, 4095).astype(np.uint16)
# encode to AVIF
avif_bytes = avif_encode(
    baseline_uint16,
    bitspersample=12,
    primaries=AVIF.COLOR_PRIMARIES.DCI_P3,
    transfer=AVIF.TRANSFER_CHARACTERISTICS.SRGB,
    speed=6,
    level=AVIF.QUALITY.LOSSLESS,
    numthreads=8,
)
with open("baseline.avif", "wb") as f:
    f.write(avif_bytes)
