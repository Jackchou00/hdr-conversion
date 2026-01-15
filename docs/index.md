# HDR Conversion

> **Note**: This project is in alpha stage. APIs may change frequently, and color conversion may have inaccuracies.
>
> Note: PyExifTool requires the exiftool executable in the system path, see [https://exiftool.org/](https://exiftool.org/) . Otherwise, reading Apple HEIC may hang without prompt. Please use `exiftool -ver` to check if it is installed correctly. This issue will be fixed in the next version.

This project provides Python-based tools for parsing, writing, and converting between various HDR image formats.

This library enables research and experimentation with HDR formats:

- **UltraHDR** - JPEG gainmap (MPF + XMP)
- **ISO 21496-1** - Adaptive gainmap standard
- **ISO 22028-5** - Pure PQ/HLG formats
- **Apple HEIC** - iOS HDR format

## Quick Start

Install using `uv` (recommended):

```bash
uv add hdr-conversion
```

Install using `pip`:

```bash
pip install hdr-conversion
```

Import the package:

```python
import hdrconv
```

## Module Overview

### Core Types (`hdrconv.core`)

Data structures for HDR representation:

- `GainmapImage` - Baseline + gainmap + metadata
- `GainmapMetadata` - ISO 21496-1 parameters
- `HDRImage` - Linear RGB + metadata
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
- `read_ultrahdr()` / `write_ultrahdr()`
- `read_22028_pq()` / `write_22028_pq()`
- `read_apple_heic()`

### Identification (`hdrconv.identify`)

Format detection utilities:

*Check for gainmap presence, only for Apple HEIC*

- `has_gain_map()` 

## Documentation Sections

- **[API Reference](api/index.md)** - API documentation
- **[Examples](examples.md)** - Practical use cases

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

## License

MIT License. See [LICENSE](https://github.com/Jackchou00/hdr-conversion/blob/main/LICENSE) for details.
