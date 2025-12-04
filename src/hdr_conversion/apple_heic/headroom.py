"""
Apple uses headroom, instead of GainMap Min and Max.

Reference: https://developer.apple.com/documentation/appkit/applying-apple-hdr-effect-to-your-photos

e.g. hdr_rgb = sdr_rgb * (1.0 + (headroom - 1.0) * gainmap)

rgb and gainmap here all in linear space, gainmap defaultly use a Rec.709 transfer function.

Code below shows how to extract the "headroom" from a file's EXIF part.

Original code: https://github.com/johncf/apple-hdr-heic/blob/master/src/apple_hdr_heic/metadata.py
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from exiftool import ExifToolHelper


@dataclass(kw_only=True, slots=True)
class AppleHDRMetadata:
    maker33: float | None = None
    maker48: float | None = None
    profile_desc: str | None = None
    hdrgainmap_version: int | None = None
    hdrgainmap_headroom: float | None = None
    aux_type: str | None = None

    @classmethod
    def from_file(cls, file_name: str | Path) -> AppleHDRMetadata:
        metadata = cls()
        # we are primarily interested in maker tags 33 (0x0021) and 48 (0x0030)
        # see https://github.com/exiftool/exiftool/blob/405674e0/lib/Image/ExifTool/Apple.pm
        tag_patterns = [
            "XMP:HDR*",
            "Apple:HDR*",
            "ICC_Profile:ProfileDesc*",
            "Quicktime:Auxiliary*",
        ]
        with ExifToolHelper() as et:
            tags = et.get_tags(file_name, tags=tag_patterns)[0]
            for tag, val in tags.items():
                if tag == "XMP:HDRGainMapVersion":
                    metadata.hdrgainmap_version = val
                elif tag == "XMP:HDRGainMapHeadroom":
                    metadata.hdrgainmap_headroom = val
                elif tag == "MakerNotes:HDRHeadroom":
                    metadata.maker33 = val
                elif tag == "MakerNotes:HDRGain":
                    metadata.maker48 = val
                elif tag == "ICC_Profile:ProfileDescription":
                    metadata.profile_desc = val
                elif tag == "Quicktime:AuxiliaryImageType":
                    metadata.aux_type = val
        return metadata

    def compute_headroom(self) -> float:
        # ref https://developer.apple.com/documentation/appkit/images_and_pdf/applying_apple_hdr_effect_to_your_photos
        assert self.maker33 is not None and self.maker48 is not None
        if self.maker33 < 1.0:
            if self.maker48 <= 0.01:
                stops = -20.0 * self.maker48 + 1.8
            else:
                stops = -0.101 * self.maker48 + 1.601
        else:
            if self.maker48 <= 0.01:
                stops = -70.0 * self.maker48 + 3.0
            else:
                stops = -0.303 * self.maker48 + 2.303
        return 2.0 ** max(stops, 0.0)


def get_headroom(file_name: str | Path) -> float | None:
    """
    Extracts the Apple HDR headroom value from the image file's metadata.

    Args:
        file_name (str | Path): The path to the image file.

    Returns:
        float | None: The headroom value if available, otherwise None.
    """
    metadata = AppleHDRMetadata.from_file(file_name)
    if metadata.hdrgainmap_headroom is not None:
        return metadata.hdrgainmap_headroom
    try:
        return metadata.compute_headroom()
    except AssertionError:
        return None


# --- Usage Example ---
if __name__ == "__main__":
    file_path = Path("apple_heic/IMG_6850.HEIC")  # Change this to your input file path
    metadata = AppleHDRMetadata.from_file(file_path)

    # Method 1: compute headroom from maker notes 33 and 48
    headroom = metadata.compute_headroom()
    print(f"Computed linear headroom: {headroom}")

    # Method 2: Directly use the gainmap headroom from metadata
    gainmap_headroom = metadata.hdrgainmap_headroom
    print(f"Gainmap headroom from metadata: {gainmap_headroom}")
