"""
File I/O helpers for dealing with binary image streams.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


@contextmanager
def open_binary(path: str | Path) -> Iterator[BinaryIO]:
    with Path(path).open("rb") as stream:
        yield stream


__all__ = ["open_binary"]
