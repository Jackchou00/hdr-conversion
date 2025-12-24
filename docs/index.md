# HDR Conversion Documentation

> **Note**: This project is in alpha stage. APIs may change frequently, and color conversion may have inaccuracies.

Welcome to the HDR Conversion documentation! This project provides Python-based tools for parsing, writing, and converting between various HDR image formats.

## What is HDR Conversion?

This library enables research and experimentation with HDR formats:

- **UltraHDR** - Android's HDR format
- **ISO 21496-1** - Adaptive gainmap standard
- **ISO 22028-5** - Pure PQ/HLG formats
- **Apple HEIC** - iOS HDR format

## Quick Start

```python
import hdrconv

# Read UltraHDR
data = hdrconv.io.read_21496("image.jpg")

# Convert to linear HDR
hdr = hdrconv.convert.gainmap_to_hdr(data)

# Write to ISO 22028-5
hdrconv.io.write_22028_pq(hdr, "output.pq")
```

## Features

### 📖 Reading
- Parse UltraHDR and ISO 21496-1 gainmap formats
- Extract ISO 22028-5 PQ/HLG data
- Read Apple HEIC with gainmap
- Extract metadata and ICC profiles

### ✍️ Writing
- Generate UltraHDR-compatible files
- Write ISO 21496-1 gainmap format
- Export ISO 22028-5 PQ/HLG
- Preserve metadata and color information

### 🔄 Conversion
- Gainmap ↔ HDR conversion
- Color space transformations (BT.709, P3, BT.2020)
- Transfer function conversion (linear, PQ, HLG, sRGB)
- Apple HEIC to standard formats

### 🔍 Identification
- Detect gainmap presence
- Format validation
- Metadata inspection

## Project Status

| Feature | Status | Notes |
|---------|--------|-------|
| ISO 21496-1 Read | ✅ Stable | Full parsing |
| ISO 21496-1 Write | ✅ Stable | Manual encoding |
| UltraHDR | ✅ Stable | v1.1 compliant |
| ISO 22028-5 | ✅ Stable | PQ/HLG support |
| Apple HEIC | ✅ Stable | Gainmap extraction |
| Color Conversion | ⚠️ Beta | May have inaccuracies |
| Production Ready | ❌ No | Research only |

## Installation

### Recommended: uv
```bash
uv add hdr-conversion
```

### Alternative: pip
```bash
pip install hdr-conversion
```

## Module Overview

### Core Types (`hdrconv.core`)
Data structures for HDR representation:
- `GainmapImage` - Baseline + gainmap + metadata
- `HDRImage` - Linear RGB + metadata
- `GainmapMetadata` - ISO 21496-1 parameters
- `AppleHeicData` - Apple format data

### Conversion (`hdrconv.convert`)
Format transformation algorithms:
- `gainmap_to_hdr()` / `hdr_to_gainmap()`
- `apple_heic_to_hdr()`
- `convert_color_space()`
- `apply_pq()` / `inverse_pq()`

### I/O (`hdrconv.io`)
Reading and writing functions:
- `read_21496()` / `write_21496()`
- `read_22028_pq()` / `write_22028_pq()`
- `read_apple_heic()`

### Identification (`hdrconv.identify`)
Format detection utilities:
- `has_gain_map()`

## Documentation Sections

- **[API Reference](api/index.md)** - Complete API documentation
- **[Getting Started](guides/getting-started.md)** - Installation and basic usage
- **[Supported Formats](guides/formats.md)** - Format specifications
- **[Examples](guides/examples.md)** - Practical use cases
- **[Standards Reference](standards/iso-standards.md)** - Technical details

## Use Cases

### Research & Learning
- Understand HDR format internals
- Experiment with conversion algorithms
- Analyze metadata structures

### Format Conversion
- Convert UltraHDR to broadcast formats
- Extract HDR data from Apple HEIC
- Create gainmaps from linear HDR

### Quality Analysis
- Inspect gainmap metadata
- Compare format implementations
- Validate color conversions

## Limitations

⚠️ **Important**:
- Not production-ready
- Color conversion may be inaccurate
- Edge cases may not be handled
- Performance not optimized
- API stability not guaranteed

## Contributing

This is a research project. Contributions welcome for:
- Bug fixes
- Format improvements
- Documentation
- Test cases

## License

MIT License. See [LICENSE](https://github.com/Jackchou00/hdr-conversion/blob/main/LICENSE) for details.

## Standards References

- [UltraHDR v1.1](https://developer.android.com/media/platform/hdr-image-format)
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100)

## Next Steps

1. **New to HDR?** → Read [Getting Started](guides/getting-started.md)
2. **Need examples?** → Check [Examples](guides/examples.md)
3. **Technical details?** → See [Standards Reference](standards/iso-standards.md)
4. **API details?** → Browse [API Reference](api/index.md)