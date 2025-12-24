# Standards Reference

This project implements several important HDR standards. Here's a detailed reference:

## ISO/IEC 21496-1:2024 (Adaptive Gainmap)

### Overview
Defines a gainmap-based HDR image format that adapts to different display capabilities.

### Key Components

#### Gainmap Data Structure
- **Baseline image**: SDR representation (8-bit, 3 channels)
- **Gainmap**: Multipliers for HDR reconstruction (8-bit, 1 or 3 channels)
- **Metadata**: Transformation parameters

#### Metadata Fields

| Field | Type | Purpose |
|-------|------|---------|
| `minimum_version` | int | Format version compatibility |
| `writer_version` | int | Writer implementation version |
| `baseline_hdr_headroom` | float | SDR reference level |
| `alternate_hdr_headroom` | float | HDR headroom for alternate |
| `is_multichannel` | bool | Separate gains per channel |
| `use_base_colour_space` | bool | Color space flag |
| `gainmap_min` | float[3] | Per-channel minimum gain |
| `gainmap_max` | float[3] | Per-channel maximum gain |
| `gainmap_gamma` | float[3] | Per-channel gamma curve |
| `baseline_offset` | float[3] | Per-channel baseline offset |
| `alternate_offset` | float[3] | Per-channel alternate offset |

#### Gainmap Formula
The HDR reconstruction uses this formula:

```
HDR = max(baseline, baseline * (offset + gain^gamma))
```

Where gain is stored as: `gain_stored = (gain_map_value / 255) * (gain_max - gain_min) + gain_min`

### Implementation Notes
- Manual byte stream editing for format compliance
- Support for both single-channel and multi-channel gainmaps
- Color space preservation

## ISO/IEC 22028-5:2023 (PQ/HLG Formats)

### Overview
Defines pure HDR formats without gainmaps, using transfer functions directly.

### Supported Transfer Functions

#### PQ (Perceptual Quantizer) - ST 2084
Designed for display-referred content with absolute luminance.

**Inverse EOTF** (display → linear):
```
if u8 <= 0.04045:
    linear = u8 / 12.92
else:
    linear = ((u8 + 0.055) / 1.055) ^ 2.4
```

**EOTF** (linear → display):
```
if linear <= 0.0001:
    u8 = 12.92 * linear
else:
    u8 = 1.055 * (linear ^ (1/2.4)) - 0.055
```

#### HLG (Hybrid Log-Gamma)
Designed for broadcast with backwards compatibility.

**OETF** (camera → encoded):
```
if linear <= 0.5:
    encoded = sqrt(linear * 3)
else:
    encoded = 0.17883277 * ln(12.7 * linear - 0.28466892) + 0.55991073
```

**EOTF** (encoded → display):
```
if encoded <= 0.5:
    display = (encoded ^ 2) / 3
else:
    display = (exp((encoded - 0.55991073) / 0.17883277) + 0.28466892) / 12.7
```

### Color Spaces

| Abbr | Full Name | Primary | White Point | Luminance |
|------|-----------|---------|-------------|-----------|
| bt709 | ITU-R BT.709 | Rec. 709 | D65 | SDR |
| p3 | DCI-P3 | P3 | D65 | Display |
| bt2020 | ITU-R BT.2020 | Rec. 2020 | D65 | HDR |

### Implementation Notes
- Uses `colour-science` library for conversions
- Linear RGB intermediates
- Clipping for out-of-gamut colors

## Apple HEIC Gainmap Format

### Structure
- HEIC container (ISOBMFF-based)
- Primary image (SDR, Display P3)
- Auxiliary image (gainmap, single channel)
- Headroom metadata

### Gainmap Formula
```
hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)
```

Where:
- `sdr_rgb`: 0-1 normalized Display P3 values
- `gainmap`: 0-1 normalized single-channel map
- `headroom`: HDR luminance multiplier (typically 4.0-6.0)

### Conversion Differences
| Aspect | Apple | ISO 21496-1 |
|--------|-------|-------------|
| Base color space | Display P3 | Any (configurable) |
| Gainmap channels | 1 | 1 or 3 |
| Offset handling | None | Full support |
| Transfer function | sRGB/linear | Any (metadata) |

## UltraHDR (Android)

### Overview
Google's HDR format for Android, based on JPEG + gainmap.

### Version History
- **v1.0** (2023): Initial release
- **v1.1** (2025): Enhanced metadata, multi-channel support

### Format Structure
```
JPEG Header
├── SOI
├── APP1 (Exif)
├── APP2 (ICC Profile - optional)
├── Data
│   ├── SDR JPEG (baseline)
│   └── Gainmap (in metadata)
└── EOI
```

### Metadata Boxes
- `HdrImageType` - Format identifier
- `GainMapImage` - Gainmap data
- `GainMapMetadata` - Transformation parameters

### Compatibility
Based on ISO 21496-1 with Android-specific extensions.

## Color Space Conversions

### RGB → RGB Matrix
Converting between primaries using 3×3 matrix:

```
[R']   [M]   [R]
[G'] = [ ] * [G]
[B']   [M]   [B]
```

Where M is derived from:
- Source primaries (x, y)
- Target primaries (x, y)
- Reference white point

### Using colour-science
```python
M = colour.matrix_RGB_to_RGB(
    colour.RGB_COLOURSPACES[target_space],
    colour.RGB_COLOURSPACES[source_space]
)
```

## Validation

When implementing, verify:

1. **Metadata compliance** - All required fields present
2. **Color accuracy** - Delta E < 1.0 for conversion
3. **Range preservation** - Min/max values in bounds
4. **Round-trip** - A → B → A preserves data

## References

- [ISO 21496-1 Specification](https://www.iso.org/standard/86775.html)
- [ISO 22028-5 Specification](https://www.iso.org/standard/81863.html)
- [UltraHDR Spec](https://developer.android.com/media/platform/hdr-image-format)
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100)
- [SMPTE ST 2084](https://www.smpte.org/st2084)