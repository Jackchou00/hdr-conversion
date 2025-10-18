"""
High-level conversion helpers that orchestrate handlers and interpreters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .formats import FormatHandler
from .interpreters.gainmap import GainmapComposer
from .interpreters.single_layer import SingleLayerComposer
from .models import ImageContainer, ImageType, IntermediateRendering
from .registry import available_handlers, get_handler


def decode_container(path: str | Path, format_name: Optional[str] = None) -> ImageContainer:
    """
    Decode an image container from the file on disk.
    """
    path = Path(path)
    if format_name is not None:
        handler = get_handler(format_name)
        with path.open("rb") as stream:
            return handler.read(stream)

    with path.open("rb") as stream:
        handler = _identify_handler(stream)
        return handler.read(stream)


def to_intermediate(
    container: ImageContainer, composer_hint: Optional[str] = None
) -> IntermediateRendering:
    """
    Convert a decoded container into the canonical intermediate rendering.
    """
    composer = _select_composer(container, composer_hint)
    return composer.compose(container)


def _identify_handler(stream) -> FormatHandler:
    original_pos = stream.tell()
    for handler in available_handlers().values():
        stream.seek(original_pos)
        if handler.identify(stream):
            stream.seek(original_pos)
            return handler
    stream.seek(original_pos)
    raise ValueError("Unable to identify handler for provided stream.")


def _select_composer(
    container: ImageContainer, composer_hint: Optional[str] = None
):
    if composer_hint == "gainmap":
        return GainmapComposer()
    if composer_hint == "single-layer":
        return SingleLayerComposer()

    if any(image.image_type == ImageType.GAINMAP for image in container.images):
        return GainmapComposer()
    return SingleLayerComposer()


__all__ = ["decode_container", "to_intermediate"]
