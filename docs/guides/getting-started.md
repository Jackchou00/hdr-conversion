# Getting Started

## Installation

### Using uv (recommended)
```bash
uv add hdr-conversion
```

### Using pip
```bash
pip install hdr-conversion
```

## Basic Usage

### Import the package
```python
import hdrconv
```

### Reading HDR Formats

#### ISO 21496-1 (Adaptive Gainmap)
```python
# Read gainmap format
data = hdrconv.io.read_21496("input.jxl")
# Returns: GainmapImage with baseline, gainmap, and metadata
```

#### ISO 22028-5 (PQ/HLG)
```python
# Read pure PQ format
hdr = hdrconv.io.read_22028_pq("input.pq")
# Returns: HDRImage with data and metadata
```

#### Apple HEIC
```python
# Read Apple HEIC with gainmap
heic_data = hdrconv.io.read_apple_heic("IMG_1234.HEIC")
# Returns: AppleHeicData with base, gainmap, and headroom
```

### Converting Formats

#### Gainmap to HDR
```python
# Convert gainmap to linear HDR
hdr_image = hdrconv.convert.gainmap_to_hdr(data)
# Returns: HDRImage in specified color space
```

#### HDR to Gainmap
```python
# Convert HDR back to gainmap format
gainmap_data = hdrconv.convert.hdr_to_gainmap(hdr_image)
# Returns: GainmapImage
```

#### Apple HEIC to HDR
```python
# Convert Apple HEIC to linear HDR
hdr = hdrconv.convert.apple_heic_to_hdr(heic_data)
# Returns: HDRImage (Display P3, linear)
```

### Color Space Conversion

```python
# Convert between color spaces
rgb_p3 = hdrconv.convert.convert_color_space(
    rgb_bt2020,
    source_space='bt2020',
    target_space='p3'
)
```

### Format Identification

```python
# Check if Apple HEIC has gainmap
has_gainmap = hdrconv.identify.has_gain_map(heic_file)
```

## Complete Example

```python
import hdrconv

# 1. Read input
data = hdrconv.io.read_21496("ultrahdr.jpg")

# 2. Convert to HDR
hdr = hdrconv.convert.gainmap_to_hdr(data)

# 3. Convert color space if needed
hdr_bt2020 = hdrconv.convert.convert_color_space(
    hdr['data'],
    source_space=hdr['color_space'],
    target_space='bt2020'
)

# 4. Write to ISO 22028-5 format
hdrconv.io.write_22028_pq(
    {"data": hdr_bt2020, "color_space": "bt2020", "transfer_function": "pq"},
    "output.pq"
)
```

## Data Types

All functions use consistent TypedDict structures:

- [`GainmapImage`](../api/core.md#hdrconv.core.GainmapImage) - Baseline + gainmap + metadata
- [`HDRImage`](../api/core.md#hdrconv.core.HDRImage) - Linear RGB + metadata
- [`GainmapMetadata`](../api/core.md#hdrconv.core.GainmapMetadata) - ISO 21496-1 parameters
- [`AppleHeicData`](../api/core.md#hdrconv.core.AppleHeicData) - Apple format data

## Next Steps

- Read the [Supported Formats](formats.md) guide
- Check the [API Reference](../api/index.md) for detailed documentation
- Look at [Examples](examples.md) for more use cases