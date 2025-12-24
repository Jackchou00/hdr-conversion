# Supported Formats

This project supports multiple HDR image formats for research and conversion purposes.

## UltraHDR (Android)

**Standard**: UltraHDR v1.1 (April 2025)
**File Extension**: `.jpg`, `.jxl`
**Structure**: JPEG with gainmap metadata

### Features
- ✅ Reading and parsing
- ✅ Writing with manual byte editing
- ✅ Conversion to/from gainmap format
- ✅ Metadata extraction

### Example
```python
data = hdrconv.io.read_21496("ultrahdr.jpg")
hdr = hdrconv.convert.gainmap_to_hdr(data)
```

## ISO 21496-1 (Adaptive Gainmap)

**Standard**: ISO/IEC 21496-1:2024
**File Extension**: `.jxl`, `.jpg`
**Structure**: Gainmap-based HDR format

### Features
- ✅ Full parsing support
- ✅ Metadata extraction (min/max/gamma/offset)
- ✅ Multi-channel gainmap support
- ✅ Color space handling

### Metadata Fields
- `baseline_hdr_headroom` - HDR headroom for baseline
- `alternate_hdr_headroom` - HDR headroom for alternate
- `gainmap_min`, `gainmap_max`, `gainmap_gamma` - Transformation parameters
- `baseline_offset`, `alternate_offset` - Offset values
- `is_multichannel` - Channel configuration
- `use_base_colour_space` - Color space flag

## ISO 22028-5 (PQ/HLG)

**Standard**: ISO/IEC 22028-5:2023
**File Extension**: `.pq`, `.hlg`
**Structure**: Pure HDR formats

### Supported Transfer Functions
- **PQ** (Perceptual Quantizer) - ST 2084
- **HLG** (Hybrid Log-Gamma) - BT.2111

### Supported Color Spaces
- BT.709 (SDR)
- DCI-P3
- BT.2020 (UHD)

### Features
- ✅ Reading PQ/HLG files
- ✅ Writing PQ/HLG files
- ✅ Color space conversion
- ✅ Transfer function conversion

### Example
```python
# Read PQ file
hdr = hdrconv.io.read_22028_pq("image.pq")

# Convert to HLG
hlg_data = hdrconv.convert.apply_pq(hdr['data'])  # If needed
```

## Apple HEIC (with Gainmap)

**File Extension**: `.heic`, `.HEIC`
**Structure**: HEIC container with Apple gainmap

### Features
- ✅ Reading Apple HEIC format
- ✅ Gainmap extraction
- ✅ Headroom metadata
- ✅ Conversion to linear HDR

### Apple Formula
```
hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)
```

### Example
```python
heic = hdrconv.io.read_apple_heic("IMG_1234.HEIC")
hdr = hdrconv.convert.apple_heic_to_hdr(heic)
```

## Format Comparison

| Format | Type | Standard | Complexity | Use Case |
|--------|------|----------|------------|----------|
| UltraHDR | Gainmap | Android | Medium | Mobile HDR |
| ISO 21496-1 | Gainmap | ISO | High | Professional |
| ISO 22028-5 | Pure HDR | ISO | Low | Broadcast |
| Apple HEIC | Gainmap | Apple | Medium | iOS devices |

## Conversion Workflows

### Gainmap ↔ HDR
```python
# Read gainmap format
data = hdrconv.io.read_21496("input.jxl")

# Convert to HDR
hdr = hdrconv.convert.gainmap_to_hdr(data)

# Convert back to gainmap
new_gainmap = hdrconv.convert.hdr_to_gainmap(hdr)
```

### Between Color Spaces
```python
# Convert from P3 to BT.2020
hdr_bt2020 = hdrconv.convert.convert_color_space(
    hdr_p3,
    source_space='p3',
    target_space='bt2020'
)
```

### Apple to Standard
```python
# Apple HEIC to ISO 21496-1
heic = hdrconv.io.read_apple_heic("apple.heic")
hdr = hdrconv.convert.apple_heic_to_hdr(heic)
gainmap = hdrconv.convert.hdr_to_gainmap(hdr)
hdrconv.io.write_21496(gainmap, "output.jxl")
```

## Limitations

⚠️ **Important Notes**:
- This is research software, not production-ready
- Color conversion may have inaccuracies
- Some edge cases may not be handled
- Always verify output quality

## Standards References

- [UltraHDR Specification](https://developer.android.com/media/platform/hdr-image-format)
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)
- [Apple HEIC](https://developer.apple.com/documentation/imageio/heic)