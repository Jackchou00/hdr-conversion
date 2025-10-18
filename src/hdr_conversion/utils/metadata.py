"""
Helpers for reading HDR-related metadata from container formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - optional dependency
    from exiftool import ExifToolHelper
except ImportError:  # pragma: no cover - optional dependency
    ExifToolHelper = None


@dataclass(slots=True)
class AppleHDRMetadata:
    """
    Selected metadata fields used for Apple gain map reconstruction.
    """

    maker33: float | None = None
    maker48: float | None = None
    profile_desc: str | None = None
    hdrgainmap_version: int | None = None
    hdrgainmap_headroom: float | None = None
    aux_type: str | None = None

    @classmethod
    def from_file(cls, file_name: str | Path) -> "AppleHDRMetadata":
        if ExifToolHelper is None:
            raise RuntimeError(
                "exiftool package is required to extract Apple HDR metadata."
            )

        metadata = cls()
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
        """
        Estimate headroom from maker note fields when direct metadata is absent.
        """
        if self.maker33 is None or self.maker48 is None:
            raise ValueError("Maker note fields are required to compute headroom.")

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


def get_headroom(file_name: str | Path) -> Optional[float]:
    """
    Extracts the Apple HDR headroom value from the image file's metadata.
    """
    metadata = AppleHDRMetadata.from_file(file_name)
    if metadata.hdrgainmap_headroom is not None:
        return metadata.hdrgainmap_headroom
    try:
        return metadata.compute_headroom()
    except ValueError:
        return None


__all__ = ["AppleHDRMetadata", "get_headroom"]
