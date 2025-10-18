"""
Abstract base for turning format-specific components into intermediate HDR data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ImageContainer, IntermediateRendering


class Composer(ABC):
    """
    Convert a decode container into the canonical intermediate rendering.
    """

    @abstractmethod
    def compose(self, container: ImageContainer) -> IntermediateRendering:
        """
        Create an intermediate rendering from the container components.
        """


__all__ = ["Composer"]
