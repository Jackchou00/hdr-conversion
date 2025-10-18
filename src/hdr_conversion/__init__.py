"""
Public package interface for the HDR conversion toolkit.
"""

from .converter import decode_container, to_intermediate
from .formats import FormatHandler, HeicPQHandler
from .interpreters import (
    GainmapComposer,
    GainmapGenerator,
    GainmapOptions,
    SingleLayerComposer,
    SingleLayerGenerator,
    TransferOptions,
)
from .models import (
    BT2020_LINEAR,
    DISPLAY_P3,
    REC2020,
    REC709,
    Image,
    ImageContainer,
    ImageType,
    IntermediateRendering,
)
from .registry import available_handlers, get_handler, register_handler

__all__ = [
    "BT2020_LINEAR",
    "DISPLAY_P3",
    "REC2020",
    "REC709",
    "GainmapComposer",
    "GainmapGenerator",
    "GainmapOptions",
    "SingleLayerComposer",
    "SingleLayerGenerator",
    "TransferOptions",
    "Image",
    "ImageContainer",
    "ImageType",
    "IntermediateRendering",
    "FormatHandler",
    "HeicPQHandler",
    "decode_container",
    "to_intermediate",
    "available_handlers",
    "get_handler",
    "register_handler",
]
