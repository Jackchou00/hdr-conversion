"""
Minimal command line interface for experimentation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .converter import decode_container, to_intermediate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decode HDR gain map assets.")
    parser.add_argument("source", type=Path, help="Path to the source image file.")
    parser.add_argument(
        "--format",
        dest="format_name",
        default=None,
        help="Explicitly specify the input format handler.",
    )
    parser.add_argument(
        "--composer",
        dest="composer_hint",
        default=None,
        choices=("gainmap", "single-layer"),
        help="Force a specific composer implementation.",
    )

    args = parser.parse_args(argv)

    container = decode_container(args.source, args.format_name)
    rendering = to_intermediate(container, args.composer_hint)

    print(f"Decoded {len(container.images)} image(s).")
    print(f"Intermediate rendering shape: {rendering.shape}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
