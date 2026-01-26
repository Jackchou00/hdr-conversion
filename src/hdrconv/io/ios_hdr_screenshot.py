"""iOS HDR Screenshot (HEIC) I/O operations.

This module provides functions for reading iOS HDR screenshots (HEIC format)
that contain a main image and a three-channel gainmap used for HDR reconstruction.

iOS HDR screenshots use a tile-based HEVC encoding with:
- Main image stored as hvc1 tiles (first group)
- Gainmap stored as hvc1 tiles (second group)
- Metadata stored in tmap item containing gainmapmax and offset values

The format can be converted to HDR using the standard ISO 21496-1 gainmap formula
with gainmap_min=0 and gamma=1.

Public APIs:
    - `read_ios_hdr_screenshot`: Read iOS HDR screenshot HEIC to GainmapImage

Note:
    Requires external tools: MP4Box (from GPAC) and ffmpeg.
    Both must be available in PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
from typing import Optional, Tuple

import numpy as np
import pillow_heif
from PIL import Image

from hdrconv.core import GainmapImage, GainmapMetadata


def _check_dependencies() -> Tuple[bool, list[str]]:
    """Check if required external tools are available.

    Returns:
        Tuple of (all_available, missing_tools_list)
    """
    missing = []
    if shutil.which("MP4Box") is None:
        missing.append("MP4Box (from GPAC package)")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    return len(missing) == 0, missing


def _get_original_resolution(filepath: str) -> Tuple[int, int]:
    """Get the original image resolution from HEIC metadata using pillow_heif.

    Returns:
        Tuple of (width, height) representing the actual image dimensions.
    """
    heif_file = pillow_heif.read_heif(filepath, convert_hdr_to_8bit=False)
    return heif_file.size  # (width, height)


def _get_hvc1_ids(file_path: str) -> list[int]:
    """Call MP4Box to get all hvc1 type item IDs."""
    cmd = ["MP4Box", "-info", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ids = []
    for line in result.stderr.splitlines() + result.stdout.splitlines():
        if "type hvc1" in line:
            match = re.search(r"ID\s+(\d+)", line)
            if match:
                ids.append(int(match.group(1)))
    return sorted(ids)


def _split_ids_into_groups(ids: list[int]) -> list[list[int]]:
    """Split non-contiguous IDs into separate groups."""
    if not ids:
        return []
    groups = []
    current_group = [ids[0]]
    for i in range(1, len(ids)):
        if ids[i] > ids[i - 1] + 1:
            groups.append(current_group)
            current_group = []
        current_group.append(ids[i])
    groups.append(current_group)
    return groups


def _process_tile_group(
    id_list: list[int],
    heic_path: str,
    temp_dir: str,
    grid_cols: int,
    grid_rows: int,
    tile_size: int,
    real_width: int,
    real_height: int,
) -> np.ndarray:
    """Extract and assemble tiles from one group into a complete image."""
    tile_paths = []

    # Extract each tile
    for i, item_id in enumerate(id_list):
        raw_path = os.path.join(temp_dir, f"{item_id}.hvc")
        jpg_path = os.path.join(temp_dir, f"tile_{i:03d}.jpg")

        # MP4Box dump
        param = f"{item_id}:path={raw_path}"
        subprocess.run(
            ["MP4Box", "-dump-item", param, heic_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # FFmpeg convert hvc -> jpg
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            subprocess.run(
                ["ffmpeg", "-y", "-i", raw_path, "-q:v", "2", jpg_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tile_paths.append(jpg_path)
            os.remove(raw_path)

    expected_tiles = grid_cols * grid_rows
    if len(tile_paths) != expected_tiles:
        raise ValueError(
            f"Expected {expected_tiles} tiles but extracted {len(tile_paths)}"
        )

    # Assemble tiles into canvas
    canvas_w = grid_cols * tile_size
    canvas_h = grid_rows * tile_size

    first_tile = Image.open(tile_paths[0])
    mode = first_tile.mode
    full_image = Image.new(mode, (canvas_w, canvas_h))

    for idx, img_path in enumerate(sorted(tile_paths)):
        row = idx // grid_cols
        col = idx % grid_cols
        x = col * tile_size
        y = row * tile_size
        tile = Image.open(img_path)
        full_image.paste(tile, (x, y))

    # Crop to actual dimensions
    final_image = full_image.crop((0, 0, real_width, real_height))
    return np.array(final_image)


def _parse_u16_be(data: bytes) -> list[int]:
    """Parse bytes as big-endian uint16 array."""
    if len(data) % 2 != 0:
        raise ValueError(f"tmap data length is not multiple of 2: {len(data)}")
    return [struct.unpack(">H", data[i : i + 2])[0] for i in range(0, len(data), 2)]


def _gainmapmax_from_u16_triplet(a: int, b: int, c: int) -> float:
    """Convert u16 triplet to float value."""
    return (a + b / 65535.0) / c


def _find_tmap_item_ids(file_path: str) -> list[int]:
    """Find tmap item IDs using MP4Box."""
    cmd = ["MP4Box", "-info", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ids = []
    for line in result.stderr.splitlines() + result.stdout.splitlines():
        if "Item #" in line and "type" in line and "tmap" in line:
            match = re.search(r"ID\s+(\d+)\s+type\s+(\w+)", line)
            if match and match.group(2) == "tmap":
                ids.append(int(match.group(1)))
    return ids


def _dump_tmap_bytes(file_path: str, temp_dir: str) -> Optional[bytes]:
    """Dump tmap bytes from HEIC file."""
    ids = _find_tmap_item_ids(file_path)
    if not ids:
        return None
    tmp_path = os.path.join(temp_dir, "tmap.tmp")
    param = f"{ids[0]}:path={tmp_path}"
    subprocess.run(
        ["MP4Box", "-dump-item", param, file_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not os.path.exists(tmp_path):
        return None
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    return data


def _parse_gainmapmax_offset_from_tmap(tmap_data: bytes) -> Tuple[float, float]:
    """Parse gainmapmax and offset from tmap data.

    The tmap format stores:
    - gainmapmax: at u16 indices 7,8,9
    - offset_1: at u16 indices 23,24,25
    - offset_2: at u16 indices 27,28,29 (should equal offset_1)
    """
    u16 = _parse_u16_be(tmap_data)
    gainmapmax = _gainmapmax_from_u16_triplet(u16[7], u16[8], u16[9])
    offset_1 = _gainmapmax_from_u16_triplet(u16[23], u16[24], u16[25])
    offset_2 = _gainmapmax_from_u16_triplet(u16[27], u16[28], u16[29])
    if abs(offset_1 - offset_2) < 1e-9:
        return gainmapmax, offset_1
    return gainmapmax, (offset_1 + offset_2) / 2.0


def _detect_grid_parameters(
    tile_count: int, first_tile_path: str
) -> Tuple[int, int, int]:
    """Auto-detect grid layout and tile size from the first tile.

    Returns:
        Tuple of (grid_cols, grid_rows, tile_size)
    """
    first_tile = Image.open(first_tile_path)
    tile_size = first_tile.width  # Assume square tiles

    # Common iOS grid layouts based on tile count
    if tile_count == 15:
        return 3, 5, tile_size
    elif tile_count == 12:
        return 3, 4, tile_size
    elif tile_count == 6:
        return 2, 3, tile_size
    else:
        # Try to find the best fit
        import math

        sqrt_n = int(math.sqrt(tile_count))
        for cols in range(sqrt_n, 0, -1):
            if tile_count % cols == 0:
                rows = tile_count // cols
                return cols, rows, tile_size
        return tile_count, 1, tile_size


def read_ios_hdr_screenshot(
    filepath: str,
    grid_cols: Optional[int] = None,
    grid_rows: Optional[int] = None,
    tile_size: int = 512,
    real_width: Optional[int] = None,
    real_height: Optional[int] = None,
) -> GainmapImage:
    """Read iOS HDR screenshot HEIC file.

    Extracts the main image, gainmap, and metadata from iOS HDR screenshots
    and returns a standard GainmapImage structure suitable for use with
    `gainmap_to_hdr`.

    Args:
        filepath: Path to the iOS HDR screenshot HEIC file.
        grid_cols: Number of tile columns (auto-detected if None).
        grid_rows: Number of tile rows (auto-detected if None).
        tile_size: Size of each square tile in pixels. Default: 512.
        real_width: Actual image width (auto-detected if None).
        real_height: Actual image height (auto-detected if None).

    Returns:
        GainmapImage dict containing:
        - ``baseline`` (np.ndarray): Main image, uint8, shape (H, W, 3), Display P3.
        - ``gainmap`` (np.ndarray): Gain map, uint8, shape (H, W, 3), three-channel.
        - ``metadata`` (GainmapMetadata): Contains gainmap_max, offset values.
        - ``baseline_icc`` (bytes | None): None.
        - ``gainmap_icc`` (bytes | None): None.

    Raises:
        RuntimeError: If external tools (MP4Box, ffmpeg) are not available.
        ValueError: If the file cannot be parsed or is not a valid iOS HDR screenshot.
        FileNotFoundError: If the input file does not exist.

    Note:
        Requires MP4Box (from GPAC) and ffmpeg to be installed and available in PATH.

        The gainmap_min is always 0 and gainmap_gamma is always 1 for iOS HDR screenshots.
        Both baseline_offset and alternate_offset are set to the same value extracted
        from the tmap metadata.

    See Also:
        - `gainmap_to_hdr`: Convert the returned GainmapImage to linear HDR.
    """
    # Check dependencies
    available, missing = _check_dependencies()
    if not available:
        raise RuntimeError(
            f"Missing required external tools: {', '.join(missing)}. "
            "Please install them and ensure they are in PATH."
        )

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    # Create temp directory for processing
    temp_dir = tempfile.mkdtemp(prefix="ios_hdr_")

    try:
        # Get all hvc1 IDs
        all_ids = _get_hvc1_ids(filepath)
        if not all_ids:
            raise ValueError("No hvc1 streams found in file")

        # Split into groups (main image and gainmap)
        groups = _split_ids_into_groups(all_ids)
        if len(groups) < 2:
            raise ValueError(
                "Expected at least 2 image groups (main + gainmap), "
                f"found {len(groups)}"
            )

        main_ids = groups[0]
        gainmap_ids = groups[1]

        # Auto-detect grid parameters if not provided
        if grid_cols is None or grid_rows is None:
            # Extract first tile to detect size
            first_id = main_ids[0]
            raw_path = os.path.join(temp_dir, f"{first_id}.hvc")
            jpg_path = os.path.join(temp_dir, "first_tile.jpg")

            param = f"{first_id}:path={raw_path}"
            subprocess.run(
                ["MP4Box", "-dump-item", param, filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", raw_path, "-q:v", "2", jpg_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            detected_cols, detected_rows, detected_tile_size = _detect_grid_parameters(
                len(main_ids), jpg_path
            )
            grid_cols = grid_cols or detected_cols
            grid_rows = grid_rows or detected_rows
            tile_size = detected_tile_size

            # Clean up detection files
            if os.path.exists(raw_path):
                os.remove(raw_path)
            if os.path.exists(jpg_path):
                os.remove(jpg_path)

        # Get original resolution from HEIC metadata if not provided
        if real_width is None or real_height is None:
            orig_width, orig_height = _get_original_resolution(filepath)
            real_width = real_width or orig_width
            real_height = real_height or orig_height

        # Process main image
        main_temp = os.path.join(temp_dir, "main")
        os.makedirs(main_temp, exist_ok=True)
        main_image = _process_tile_group(
            main_ids,
            filepath,
            main_temp,
            grid_cols,
            grid_rows,
            tile_size,
            real_width or canvas_w,
            real_height or canvas_h,
        )

        # Process gainmap
        gainmap_temp = os.path.join(temp_dir, "gainmap")
        os.makedirs(gainmap_temp, exist_ok=True)
        gainmap_image = _process_tile_group(
            gainmap_ids,
            filepath,
            gainmap_temp,
            grid_cols,
            grid_rows,
            tile_size,
            real_width or canvas_w,
            real_height or canvas_h,
        )

        # Parse tmap metadata
        tmap_data = _dump_tmap_bytes(filepath, temp_dir)
        if tmap_data is None:
            raise ValueError("No tmap metadata found in file")

        gainmapmax, offset = _parse_gainmapmax_offset_from_tmap(tmap_data)

        # Construct GainmapMetadata
        # iOS HDR screenshots use: gainmap_min=0, gamma=1, both offsets equal
        metadata = GainmapMetadata(
            minimum_version=0,
            writer_version=0,
            baseline_hdr_headroom=1.0,
            alternate_hdr_headroom=float(2**gainmapmax),
            is_multichannel=True,
            use_base_colour_space=True,
            gainmap_min=(0.0, 0.0, 0.0),
            gainmap_max=(gainmapmax, gainmapmax, gainmapmax),
            gainmap_gamma=(1.0, 1.0, 1.0),
            baseline_offset=(offset, offset, offset),
            alternate_offset=(offset, offset, offset),
        )

        # Ensure arrays are uint8
        if main_image.dtype != np.uint8:
            main_image = main_image.astype(np.uint8)
        if gainmap_image.dtype != np.uint8:
            gainmap_image = gainmap_image.astype(np.uint8)

        return GainmapImage(
            baseline=main_image,
            gainmap=gainmap_image,
            metadata=metadata,
            baseline_icc=None,
            gainmap_icc=None,
        )

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
