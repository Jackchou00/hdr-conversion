"""
Interpreters for single layer PQ/HLG images.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import colour

from ..models import ImageContainer, IntermediateRendering
from .composer_base import Composer
from .generator_base import Generator


@dataclass(slots=True)
class TransferOptions:
    transfer_function: str = "ITU-R BT.2100 PQ"


class SingleLayerComposer(Composer):
    """
    Compose an intermediate rendering from a single PQ/HLG encoded image.
    """

    def __init__(self, transfer_function: str = "ITU-R BT.2100 PQ") -> None:
        self.transfer_function = transfer_function

    def compose(self, container: ImageContainer) -> IntermediateRendering:
        image = container.primary()
        linear = colour.eotf(image.as_float(), self.transfer_function)
        return IntermediateRendering(linear)


class SingleLayerGenerator(Generator):
    """
    Encode an intermediate rendering into a single PQ/HLG layer.
    """

    def __init__(self, transfer_function: str = "ITU-R BT.2100 PQ") -> None:
        self.transfer_function = transfer_function

    def generate(
        self, rendering: IntermediateRendering, options: dict[str, Any] | None = None
    ) -> ImageContainer:
        raise NotImplementedError("Single-layer generation is not implemented yet.")


__all__ = [
    "SingleLayerComposer",
    "SingleLayerGenerator",
    "TransferOptions",
]
