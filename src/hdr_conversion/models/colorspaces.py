"""
Common colourspace definitions used throughout the HDR conversion pipeline.

These helper objects wrap `colour-science` models so we only construct them
once per interpreter run.  Keeping them in a dedicated module avoids circular
imports between model classes and format handlers.
"""

from __future__ import annotations

from typing import Final

import colour
from colour import RGB_Colourspace

# Working space for any intermediate linear HDR representation.
BT2020_LINEAR: Final[RGB_Colourspace] = RGB_Colourspace(
    name="BT.2020 Linear",
    primaries=((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),
    whitepoint=(0.3127, 0.3290),
    whitepoint_name="D65",
    cctf_decoding=colour.linear_function,
    cctf_encoding=colour.linear_function,
    use_derived_matrix_RGB_to_XYZ=True,
    use_derived_matrix_XYZ_to_RGB=True,
)

# Frequently used perceptual colourspaces when dealing with camera assets.
DISPLAY_P3: Final[RGB_Colourspace] = colour.RGB_COLOURSPACES["Display P3"]
REC2020: Final[RGB_Colourspace] = colour.RGB_COLOURSPACES["ITU-R BT.2020"]
REC709: Final[RGB_Colourspace] = colour.RGB_COLOURSPACES["ITU-R BT.709"]


def get_colourspace(name: str) -> RGB_Colourspace:
    """
    Look up a colourspace by name using `colour-science`.

    Raises:
        KeyError: If the colourspace is not registered.
    """
    try:
        return colour.RGB_COLOURSPACES[name]
    except KeyError as exc:  # pragma: no cover - thin wrapper for clarity
        raise KeyError(f"Unknown colourspace '{name}'.") from exc


__all__ = [
    "BT2020_LINEAR",
    "DISPLAY_P3",
    "REC2020",
    "REC709",
    "get_colourspace",
]
