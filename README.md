# HDR Conversion

## Introduction

High Dynamic Range (HDR) images are becoming increasingly popular in photography. This repository provides a Python script to convert between multiple HDR formats, including UltraHDR, Gainmap (ISO 21496-1) and pure PQ or HLG (ISO 22028-5).

## Structure

The main idea in HDR format conversion is to convert the image to a linear light space, and from linear light space to the target format.

## References

- [UltraHDR](https://developer.android.com/media/platform/hdr-image-format): version 1.1 at 04.2025.
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)

## Requirements

- colour-science: for transfer functions and colour space conversions.
- libultrahdr: for UltraHDR format reading (metadata only) and writing.
- pillow-heif: for AVIF format reading and writing.
