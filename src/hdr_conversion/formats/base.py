"""
Abstract base class for format handlers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO

from ..models import ImageContainer


class FormatHandler(ABC):
    """
    Bridge between a concrete file format and the in-memory model.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human readable name for the format."""

    @abstractmethod
    def identify(self, stream: BinaryIO) -> bool:
        """
        Determine if the bytes in ``stream`` match this format.
        """

    @abstractmethod
    def read(self, stream: BinaryIO) -> ImageContainer:
        """
        Decode the file into an :class:`ImageContainer`.
        """

    @abstractmethod
    def write(self, stream: BinaryIO, container: ImageContainer) -> None:
        """
        Encode an :class:`ImageContainer` back into the format.
        """


__all__ = ["FormatHandler"]
