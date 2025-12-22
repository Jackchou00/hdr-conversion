# HDR Format Conversion Tool

## Project Overview

This project provides Python-based research on HDR format parsing and writing, supporting parsing, writing, and conversion of multiple formats including UltraHDR, Adaptive Gainmap (ISO 21496-1), and pure PQ/HLG formats (ISO 22028-5).

Note: This project is for research and learning purposes only and does not aim for production readiness.

## Features

### Parsing

For UltraHDR and Adaptive Gainmap formats, supports structured extraction of:

- Main image data
- Gainmap image data
- Gainmap metadata

For pure PQ/HLG formats, supports extraction of image data and related metadata.

### Writing

Writes image data and structured metadata into corresponding formats.

UltraHDR and Adaptive Gainmap formats are implemented through manual byte stream editing combined with existing library JPEG encoding capabilities, while pure PQ/HLG formats are implemented through existing libraries.

### Conversion

Calculates alternate images based on metadata to enable conversion between Gainmap and pure HDR formats.

## Reference Standards

- [UltraHDR](https://developer.android.com/media/platform/hdr-image-format): Version 1.1 released in April 2025
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)

## License

MIT. Please refer to the respective LICENSE files for specific format and dependency details.
