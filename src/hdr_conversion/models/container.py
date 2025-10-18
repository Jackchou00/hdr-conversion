"""
Logical grouping of related images and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, MutableMapping

from .image import Image


@dataclass(slots=True)
class ImageContainer:
    """
    Bundles one or more related images with associated metadata.

    Most HDR-capable formats encapsulate multiple rasters (e.g. SDR base layer
    and a gain map).  This class provides a consistent representation that both
    format handlers and interpreters can operate on.
    """

    images: List[Image]
    metadata: MutableMapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.images, list):
            self.images = list(self.images)
        if any(not isinstance(image, Image) for image in self.images):
            raise TypeError("images must contain only Image instances.")

    @classmethod
    def from_iterable(
        cls, images: Iterable[Image], metadata: MutableMapping[str, Any] | None = None
    ) -> "ImageContainer":
        return cls(list(images), metadata or {})

    def primary(self) -> Image:
        """
        Convenience accessor for the first image in the container.
        """
        if not self.images:
            raise ValueError("ImageContainer does not contain any images.")
        return self.images[0]


__all__ = ["ImageContainer"]
