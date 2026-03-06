import struct
from pathlib import Path

import numpy as np


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset : offset + 4])[0]


def _s15f16(data: bytes, offset: int) -> float:
    return struct.unpack(">i", data[offset : offset + 4])[0] / 65536.0


def _ascii(data: bytes, offset: int, length: int) -> str:
    return (
        data[offset : offset + length].decode("ascii", errors="replace").rstrip("\x00")
    )


def _read_icc_bytes(icc_source: bytes | str | Path) -> tuple[bytes, str]:
    if isinstance(icc_source, bytes):
        return icc_source, "<bytes>"

    path = Path(icc_source)
    return path.read_bytes(), path.name


def _parse_xyz(data: bytes, offset: int, size: int) -> dict[str, object]:
    value_count = max((size - 8) // 12, 0)
    values = []

    for i in range(value_count):
        xyz_offset = offset + 8 + i * 12
        values.append(
            [
                _s15f16(data, xyz_offset),
                _s15f16(data, xyz_offset + 4),
                _s15f16(data, xyz_offset + 8),
            ]
        )

    return {"type": "XYZ", "count": value_count, "values": values}


def decode_icc_colorants(icc_source: bytes | str | Path) -> dict[str, object]:
    data, file_name = _read_icc_bytes(icc_source)
    result: dict[str, object] = {
        "file_name": file_name,
        "tag_data": {},
    }

    tag_count = _u32(data, 128)
    result["tag_count"] = tag_count

    for i in range(tag_count):
        off = 132 + i * 12
        sig = _ascii(data, off, 4)
        data_off = _u32(data, off + 4)
        data_size = _u32(data, off + 8)
        tag_type = data[data_off : data_off + 4]

        if tag_type == b"XYZ ":
            result["tag_data"][sig] = _parse_xyz(data, data_off, data_size)
        else:
            result["tag_data"][sig] = None

    return result


def _require_xyz_triplet(tag_data: dict[str, object], tag_name: str) -> np.ndarray:
    xyz_tag = tag_data.get(tag_name)
    if xyz_tag is None:
        raise ValueError(f"tag not found in ICC profile: {tag_name}")

    if xyz_tag.get("type") != "XYZ" or xyz_tag.get("count") < 1:
        raise ValueError(f"unsupported ICC tag format: {tag_name}")

    return np.asarray(xyz_tag["values"][0], dtype=np.float64)


def read_icc_primaries_matrix(icc_source: bytes | str | Path) -> np.ndarray:
    result = decode_icc_colorants(icc_source)
    tag_data = result["tag_data"]
    red_xyz = _require_xyz_triplet(tag_data, "rXYZ")
    green_xyz = _require_xyz_triplet(tag_data, "gXYZ")
    blue_xyz = _require_xyz_triplet(tag_data, "bXYZ")

    return np.column_stack([red_xyz, green_xyz, blue_xyz]).astype(np.float64)


def read_icc_whitepoint(icc_source: bytes | str | Path) -> np.ndarray:
    result = decode_icc_colorants(icc_source)
    return _require_xyz_triplet(result["tag_data"], "wtpt")


def build_icc_conversion_matrix(
    source_icc: bytes | str | Path, target_icc: bytes | str | Path
) -> np.ndarray:
    source_matrix = read_icc_primaries_matrix(source_icc)
    target_matrix = read_icc_primaries_matrix(target_icc)
    return np.linalg.inv(target_matrix) @ source_matrix


def convert_array_with_icc_matrix(
    source_icc: bytes | str | Path,
    target_icc: bytes | str | Path,
    img_array: np.ndarray,
) -> np.ndarray:
    conversion_matrix = build_icc_conversion_matrix(source_icc, target_icc)
    img_array = np.asarray(img_array, dtype=np.float32)
    return np.tensordot(img_array, conversion_matrix.T, axes=([-1], [0]))
