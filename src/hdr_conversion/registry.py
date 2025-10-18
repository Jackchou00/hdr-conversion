"""
Simple registry used to look up format handlers by name.
"""

from __future__ import annotations

from typing import Dict

from .formats import FormatHandler
from .formats.heic_pq import HeicPQHandler

_HANDLERS: Dict[str, FormatHandler] = {}


def register_handler(handler: FormatHandler) -> None:
    _HANDLERS[handler.name] = handler


def get_handler(name: str) -> FormatHandler:
    try:
        return _HANDLERS[name]
    except KeyError as exc:
        raise KeyError(f"No handler registered under name '{name}'.") from exc


def available_handlers() -> Dict[str, FormatHandler]:
    return dict(_HANDLERS)


def _register_defaults() -> None:
    register_handler(HeicPQHandler())


_register_defaults()


__all__ = ["register_handler", "get_handler", "available_handlers"]
