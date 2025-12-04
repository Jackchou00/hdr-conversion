# HDR Format Conversion Tool

## Introduction

High Dynamic Range (HDR) image format has gained significant traction in modern photography. This repository offers a Python-based solution for converting between various HDR formats, including UltraHDR, Gainmap (ISO 21496-1), and pure PQ/HLG formats (ISO 22028-5).

Note: This project is for research and learning purposes and is not intended to provide industry-grade robustness or production readiness.

## Architecture Overview

The core conversion methodology involves transforming images into a linear light color space as an intermediate representation, followed by conversion to the desired target format.

## References

- [UltraHDR](https://developer.android.com/media/platform/hdr-image-format): Version 1.1 as of April 2025
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)

## Dependencies

- `colour-science`: Handles transfer functions and color space conversions
- `libultrahdr`: Provides UltraHDR format support (metadata reading and full writing capabilities)
- `pillow-heif`: Enables AVIF format input/output operations

## Roadmap

- Implement comprehensive HDR format identification system
- Enhance Gainmap reader implementation beyond current `FF D9 FF D8` pattern matching
- Migrate from `pillow_heif` to standard `pillow` library for AVIF support
- Integrate Apple HEIC format into current input/output operations
