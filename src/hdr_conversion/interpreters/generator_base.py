"""
Abstract base for producing format-specific payloads from an intermediate rendering.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ImageContainer, IntermediateRendering


class Generator(ABC):
    """
    Generate the container required by a specific output format.
    """

    @abstractmethod
    def generate(
        self, rendering: IntermediateRendering, options: dict[str, Any] | None = None
    ) -> ImageContainer:
        """
        Produce an image container for a given format.
        """


__all__ = ["Generator"]
