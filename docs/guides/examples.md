# Examples

## Basic Conversion Workflow

Reading UltraHDR and converting to ISO 22028-5 PQ format:

```python
import hdrconv
import numpy as np

# 1. Read UltraHDR file
data = hdrconv.io.read_21496("ultrahdr.jpg")

print(f"Baseline shape: {data['baseline'].shape}")
print(f"Gainmap shape: {data['gainmap'].shape}")
print(f"Metadata: {data['metadata']}")

# 2. Convert to linear HDR
hdr = hdrconv.convert.gainmap_to_hdr(data)

print(f"HDR color space: {hdr['color_space']}")
print(f"Transfer function: {hdr['transfer_function']}")

# 3. Convert to BT.2020 for broadcast
hdr_bt2020 = hdrconv.convert.convert_color_space(
    hdr['data'],
    source_space=hdr['color_space'],
    target_space='bt2020'
)

# 4. Write as PQ format
hdrconv.io.write_22028_pq(
    {
        "data": hdr_bt2020,
        "color_space": "bt2020",
        "transfer_function": "pq",
        "icc_profile": None
    },
    "output.pq"
)
```

## Batch Processing

Process multiple files in a directory:

```python
import hdrconv
from pathlib import Path

input_dir = Path("input_images")
output_dir = Path("output_hdr")
output_dir.mkdir(exist_ok=True)

for jpg_file in input_dir.glob("*.jpg"):
    try:
        # Read and convert
        data = hdrconv.io.read_21496(str(jpg_file))
        hdr = hdrconv.convert.gainmap_to_hdr(data)

        # Save with new extension
        output_path = output_dir / f"{jpg_file.stem}.pq"
        hdrconv.io.write_22028_pq(hdr, str(output_path))

        print(f"Converted: {jpg_file.name} -> {output_path.name}")

    except Exception as e:
        print(f"Error processing {jpg_file.name}: {e}")
```

## Apple HEIC to Standard HDR

Converting Apple HEIC gainmap format to standard HDR:

```python
import hdrconv

# Read Apple HEIC
heic_data = hdrconv.io.read_apple_heic("IMG_1234.HEIC")

print(f"Base image: {heic_data['base'].shape}")
print(f"Gainmap: {heic_data['gainmap'].shape}")
print(f"Headroom: {heic_data['headroom']}")

# Convert to linear HDR (Display P3)
hdr = hdrconv.convert.apple_heic_to_hdr(heic_data)

# Convert to BT.2020 if needed
hdr_bt2020 = hdrconv.convert.convert_color_space(
    hdr['data'],
    source_space='p3',
    target_space='bt2020'
)

# Now ready for writing to various formats
```

## Metadata Inspection

Reading and analyzing gainmap metadata:

```python
import hdrconv

data = hdrconv.io.read_21496("image.jxl")
metadata = data['metadata']

# Access metadata fields
print("=== Gainmap Metadata ===")
print(f"Version: {metadata.get('minimum_version', 'N/A')}")
print(f"HDR Headroom - Baseline: {metadata.get('baseline_hdr_headroom', 'N/A')}")
print(f"HDR Headroom - Alternate: {metadata.get('alternate_hdr_headroom', 'N/A')}")

print("\n=== Transformation Parameters ===")
gain_min = metadata.get('gainmap_min', (0, 0, 0))
gain_max = metadata.get('gainmap_max', (1, 1, 1))
gain_gamma = metadata.get('gainmap_gamma', (1, 1, 1))

print(f"Gainmap Min (RGB): {gain_min}")
print(f"Gainmap Max (RGB): {gain_max}")
print(f"Gainmap Gamma (RGB): {gain_gamma}")

print("\n=== Offset Parameters ===")
base_offset = metadata.get('baseline_offset', (0, 0, 0))
alt_offset = metadata.get('alternate_offset', (0, 0, 0))

print(f"Baseline Offset (RGB): {base_offset}")
print(f"Alternate Offset (RGB): {alt_offset}")

print("\n=== Channel Config ===")
print(f"Multichannel: {metadata.get('is_multichannel', False)}")
print(f"Use Base Color Space: {metadata.get('use_base_colour_space', False)}")
```

## Custom Gainmap Creation

Creating a gainmap from linear HDR data:

```python
import hdrconv
import numpy as np

# Assume we have HDR linear data
hdr_data = np.random.random((1080, 1920, 3)).astype(np.float32)

# HDRImage structure
hdr_image = {
    "data": hdr_data,
    "color_space": "bt2020",
    "transfer_function": "linear",
    "icc_profile": None
}

# Convert to gainmap format
gainmap_data = hdrconv.convert.hdr_to_gainmap(hdr_image)

print(f"Created gainmap with shape: {gainmap_data['gainmap'].shape}")
print(f"Metadata: {gainmap_data['metadata']}")

# Write to file
hdrconv.io.write_21496(gainmap_data, "custom_gainmap.jxl")
```

## Format Detection

Checking what format a file is:

```python
import hdrconv
from pathlib import Path

def detect_hdr_format(filepath):
    """Detect HDR format of a file."""
    path = Path(filepath)

    # Try different readers
    readers = [
        ("ISO 21496-1", lambda: hdrconv.io.read_21496(str(path))),
        ("Apple HEIC", lambda: hdrconv.io.read_apple_heic(str(path))),
        ("ISO 22028 PQ", lambda: hdrconv.io.read_22028_pq(str(path))),
    ]

    for format_name, reader in readers:
        try:
            result = reader()
            print(f"✓ {filepath} - {format_name}")
            return format_name, result
        except:
            continue

    print(f"✗ {filepath} - Unknown format")
    return None, None

# Use it
format_name, data = detect_hdr_format("unknown.hdr")
```

## Color Space Chain

Full workflow with color space conversions:

```python
import hdrconv

# 1. Read source (assume UltraHDR in P3)
data = hdrconv.io.read_21496("source.jpg")
hdr_p3 = hdrconv.convert.gainmap_to_hdr(data)

# 2. Convert to BT.2020
hdr_bt2020 = hdrconv.convert.convert_color_space(
    hdr_p3['data'],
    source_space='p3',
    target_space='bt2020'
)

# 3. Apply PQ transfer (if needed for delivery)
pq_data = hdrconv.convert.apply_pq(hdr_bt2020)

# 4. Write for delivery
final_output = {
    "data": pq_data,
    "color_space": "bt2020",
    "transfer_function": "pq"
}
hdrconv.io.write_22028_pq(final_output, "delivery.pq")
```

## QA with Comparison

Compare original vs converted:

```python
import hdrconv
import numpy as np

def compare_hdr_formats(original_path, converted_path):
    """Compare original and converted HDR."""

    # Read original
    orig_data = hdrconv.io.read_21496(original_path)
    orig_hdr = hdrconv.convert.gainmap_to_hdr(orig_data)

    # Read converted
    conv_hdr = hdrconv.io.read_22028_pq(converted_path)

    # Basic metrics
    orig_mean = np.mean(orig_hdr['data'])
    conv_mean = np.mean(conv_hdr['data'])

    orig_max = np.max(orig_hdr['data'])
    conv_max = np.max(conv_hdr['data'])

    print(f"Original mean: {orig_mean:.4f}, max: {orig_max:.4f}")
    print(f"Converted mean: {conv_mean:.4f}, max: {conv_max:.4f}")
    print(f"Mean diff: {abs(orig_mean - conv_mean):.4f}")

    return orig_hdr, conv_hdr

# Usage
compare_hdr_formats("ultrahdr.jpg", "converted.pq")
```

## Error Handling

Robust processing with error handling:

```python
import hdrconv
from pathlib import Path

def safe_convert(input_path, output_path):
    """Safely convert with detailed error reporting."""

    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    try:
        # Try reading as UltraHDR/ISO 21496-1
        data = hdrconv.io.read_21496(str(path))
        hdr = hdrconv.convert.gainmap_to_hdr(data)

    except Exception as e:
        print(f"Warning: Could not read as ISO 21496-1: {e}")

        # Try Apple HEIC
        try:
            heic = hdrconv.io.read_apple_heic(str(path))
            hdr = hdrconv.convert.apple_heic_to_hdr(heic)
        except:
            raise ValueError(f"Could not determine format for: {input_path}")

    # Write output
    hdrconv.io.write_22028_pq(hdr, output_path)
    print(f"Successfully converted: {input_path} -> {output_path}")

# Usage
try:
    safe_convert("input.hdr", "output.pq")
except Exception as e:
    print(f"Conversion failed: {e}")
```