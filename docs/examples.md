# Examples

See GitHub repository for complete example code: [hdr-conversion/examples](https://github.com/Jackchou00/hdr-conversion/tree/main/examples)

!!! note "External Dependencies"
    Examples below use the [`colour`](https://colour-science.readthedocs.io/) library for color space conversion and transfer functions. Install it with:
    ```bash
    uv add colour-science
    ```

## ISO 21496-1 Gainmap → PQ AVIF

Convert ISO 21496-1 Gainmap JPEG to PQ AVIF format:

```python
import hdrconv.io as io
import hdrconv.convert as convert

import colour
import numpy as np

# Read Gainmap file
gainmap_data = io.read_21496("images/iso21496.jpg")

# Prepare baseline: normalize, convert to linear light, then to BT.2020
# Note: gainmap_to_hdr requires baseline in linear light space
baseline_image = gainmap_data["baseline"].astype(np.float32) / 255.0
baseline = colour.eotf(baseline_image, function="sRGB")  # Convert to linear
baseline_bt2020 = colour.RGB_to_RGB(
    baseline, input_colourspace="Display P3", output_colourspace="ITU-R BT.2020"
)
gainmap_data["baseline"] = (baseline_bt2020 * 255.0).astype(np.uint8)

# Convert to linear HDR
hdr = convert.gainmap_to_hdr(gainmap_data)

# Apply PQ transfer function (reference white: 203 nits)
pq_encoded = colour.eotf_inverse(hdr["data"] * 203.0, function="ITU-R BT.2100 PQ")

# Write PQ AVIF
pq_data = {
    "data": pq_encoded,
    "color_space": "bt2020",
    "transfer_function": "pq",
    "icc_profile": None,
}
io.write_22028_pq(pq_data, "output.avif")
```

## Apple HEIC → PQ AVIF

Convert Apple HEIC HDR format to standard PQ AVIF:

```python
import hdrconv.io as io
import hdrconv.convert as convert

import colour
import numpy as np

# Read Apple HEIC
heic_data = io.read_apple_heic("photo.HEIC")

# Convert to linear HDR (Display P3)
hdr = convert.apple_heic_to_hdr(heic_data)

# Convert color space P3 → BT.2020
hdr_bt2020 = colour.RGB_to_RGB(
    hdr["data"], input_colourspace="Display P3", output_colourspace="ITU-R BT.2020"
)

# Apply PQ transfer function
hdr_bt2020 = np.clip(hdr_bt2020, 0.0, np.inf)
pq_encoded = colour.eotf_inverse(hdr_bt2020 * 203.0, function="ITU-R BT.2100 PQ")
pq_encoded = np.clip(pq_encoded, 0.0, 1.0)

# Write PQ AVIF
pq_data = {
    "data": pq_encoded,
    "color_space": "bt2020",
    "transfer_function": "pq",
    "icc_profile": None,
}
io.write_22028_pq(pq_data, "output.avif")
```

## Apple HEIC → Gainmap JPEG (ISO 21496-1 + UltraHDR)

Generate both ISO 21496-1 and UltraHDR JPEGs from Apple HEIC:

```python
import hdrconv.io as io
import hdrconv.convert as convert

# Read Apple HEIC
heic_data = io.read_apple_heic("photo.HEIC")

# Convert to linear HDR (Display P3)
hdr = convert.apple_heic_to_hdr(heic_data)

# Load Display P3 ICC
with open("icc/Display P3.icc", "rb") as f:
    p3_icc = f.read()

# Generate Gainmap (baseline in P3)
gainmap_data = convert.hdr_to_gainmap(
    hdr,
    baseline=None,  # Auto-generate SDR baseline
    icc_profile=p3_icc,
    gamma=1.0,
)

# Write ISO 21496-1 and UltraHDR
io.write_21496(gainmap_data, "output_iso21496.jpg")
io.write_ultrahdr(gainmap_data, "output_uhdr.jpg")
```

## PQ AVIF → ISO 21496-1 Gainmap

Convert PQ AVIF to ISO 21496-1 Gainmap format:

```python
import hdrconv.io as io
import hdrconv.convert as convert

import colour

# Read PQ AVIF
pq_data = io.read_22028_pq("image.avif")

# Convert PQ to linear HDR (reference white: 203 nits)
linear_hdr = colour.eotf(pq_data["data"], function="ITU-R BT.2100 PQ") / 203.0

hdr = {
    "data": linear_hdr,
    "color_space": "bt2020",
    "transfer_function": "linear",
}

# Load BT.2020 ICC profile
with open("icc/ITU-R_BT2020-beta.icc", "rb") as f:
    bt2020_icc = f.read()

# Generate Gainmap (auto-create SDR baseline)
gainmap_data = convert.hdr_to_gainmap(
    hdr,
    baseline=None,
    icc_profile=bt2020_icc,
    gamma=1.0,
)

# Write ISO 21496-1
io.write_21496(gainmap_data, "output_gainmap.jpg")
```

## iOS HDR Screenshot → UltraHDR

Convert iOS HDR screenshots (HEIC with tile-based HEVC) to UltraHDR:

!!! note "External Dependencies"
    Requires `MP4Box` (GPAC) and `ffmpeg`. Install on macOS: `brew install gpac ffmpeg`

```python
from hdrconv.io import read_ios_hdr_screenshot, write_ultrahdr

# Read iOS HDR screenshot
gainmap_image = read_ios_hdr_screenshot("screenshot.HEIC")

# Load and embed Display P3 ICC profile
with open("icc/Display P3.icc", "rb") as f:
    p3_icc = f.read()

gainmap_image["baseline_icc"] = p3_icc
gainmap_image["gainmap_icc"] = p3_icc

# Write directly as UltraHDR (no conversion needed)
write_ultrahdr(gainmap_image, "output_uhdr.jpg")
```