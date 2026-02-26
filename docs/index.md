# HDR Conversion

> **Important Note**: In alpha stage, API may change frequently. Currently, color conversion may be incorrect. This project is still in a very early stage, please submit issues or contact the author directly if you encounter any problems.

This project provides Python-based tools for parsing, writing, and converting between various HDR image formats.

This library enables research and experimentation with HDR formats:

- **UltraHDR** - JPEG gainmap (MPF + XMP)
- **ISO 21496-1** - Adaptive gainmap standard
- **ISO 22028-5** - Pure PQ/HLG formats
- **Apple HEIC** - iOS HDR format
- **iOS HDR Screenshot** - iOS screenshot HEIC with tile-based encoding

## Quick Start

Install using `uv` (recommended):

```bash
uv add hdr-conversion
```

Install using `pip`:

```bash
pip install hdr-conversion
```

### Install from Develop Branch

To try the latest unreleased features, install directly from the `develop` branch:

```bash
uv add git+https://github.com/Jackchou00/hdr-conversion.git --branch develop
```

```bash
pip install git+https://github.com/Jackchou00/hdr-conversion.git@develop
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

!!! note "Color Space Conversion"
    Built-in color space conversion functions have been removed. Users should implement color space conversions using external libraries like [`colour-science`](https://colour-science.readthedocs.io/). See [Examples](examples.md) for usage patterns.

### I/O (`hdrconv.io`)

Reading and writing functions:

- `read_21496()` / `write_21496()`
- `read_ultrahdr()` / `write_ultrahdr()`
- `read_22028_pq()` / `write_22028_pq()`
- `read_apple_heic()`
- `read_ios_hdr_screenshot()`

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
