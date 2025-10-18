"""
Handler helpers for single-layer HEIC/AVIF files that carry gain maps.
"""

from __future__ import annotations

import io
from typing import BinaryIO, Optional, Sequence

import numpy as np
import pillow_heif
from PIL import Image as PILImage

from ..models import Image, ImageContainer, ImageType, DISPLAY_P3, REC709
from .base import FormatHandler

# According to Apple documentation, the URN for the HDR gain map auxiliary image is fixed.
HDR_GAIN_MAP_URN = "urn:com:apple:photo:2020:aux:hdrgainmap"


def _read_heif(stream: BinaryIO) -> pillow_heif.HeifFile:
    """
    Read the entire stream into memory and decode it using pillow-heif.
    """
    data = stream.read()
    stream.seek(0)
    return pillow_heif.read_heif(io.BytesIO(data), convert_hdr_to_8bit=False)


def _as_numpy_image(heif_file: pillow_heif.HeifFile) -> np.ndarray:
    base_image_pil = PILImage.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    return np.array(base_image_pil)


def _extract_gain_map(heif_file: pillow_heif.HeifFile) -> Optional[np.ndarray]:
    gain_map_np = None
    if "aux" in heif_file.info and HDR_GAIN_MAP_URN in heif_file.info["aux"]:
        gain_map_ids: Sequence[int] = heif_file.info["aux"][HDR_GAIN_MAP_URN]
        if gain_map_ids:
            aux_image = heif_file.get_aux_image(gain_map_ids[0])
            gain_map_pil = PILImage.frombytes(
                aux_image.mode,
                aux_image.size,
                aux_image.data,
                "raw",
                aux_image.mode,
                aux_image.stride,
            )
            gain_map_np = np.array(gain_map_pil)
    return gain_map_np


class HeicPQHandler(FormatHandler):
    """
    Basic handler for HEIC files that follow Apple's gain map conventions.
    """

    @property
    def name(self) -> str:
        return "heic-pq"

    def identify(self, stream: BinaryIO) -> bool:
        header = stream.read(12)
        stream.seek(0)
        if len(header) < 12 or header[4:8] != b"ftyp":
            return False
        major_brand = header[8:12]
        return major_brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1"}

    def read(self, stream: BinaryIO) -> ImageContainer:
        heif_file = _read_heif(stream)
        base_image_np = _as_numpy_image(heif_file)
        gain_map_np = _extract_gain_map(heif_file)

        images = [
            Image(
                content=base_image_np,
                colorspace=DISPLAY_P3,
                image_type=ImageType.SDR,
            )
        ]

        if gain_map_np is not None:
            images.append(
                Image(
                    content=gain_map_np,
                    colorspace=REC709,
                    image_type=ImageType.GAINMAP,
                )
            )
        metadata = dict(heif_file.info)
        return ImageContainer(images=images, metadata=metadata)

    def write(self, stream: BinaryIO, container: ImageContainer) -> None:
        raise NotImplementedError("Writing HEIC gain map files is not implemented yet.")


__all__ = ["HeicPQHandler", "HDR_GAIN_MAP_URN"]
