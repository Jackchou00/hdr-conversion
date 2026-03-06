import struct
from pathlib import Path
from typing import Any, Dict
import numpy as np


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset : offset + 4])[0]


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack(">H", data[offset : offset + 2])[0]


def _s15f16(data: bytes, offset: int) -> float:
    return struct.unpack(">i", data[offset : offset + 4])[0] / 65536.0


def _u8f8(data: bytes, offset: int) -> float:
    return struct.unpack(">H", data[offset : offset + 2])[0] / 256.0


def _ascii(data: bytes, offset: int, length: int) -> str:
    return (
        data[offset : offset + length].decode("ascii", errors="replace").rstrip("\x00")
    )


def _read_icc_bytes(icc_source: bytes | str | Path) -> tuple[bytes, str]:
    if isinstance(icc_source, bytes):
        return icc_source, "<bytes>"

    path = Path(icc_source)
    return path.read_bytes(), path.name


def _parse_curv(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    count = _u32(data, offset + 8)
    if count == 0:
        return {"type": "curv", "count": 0, "values": []}
    if count == 1:
        return {"type": "curv", "count": 1, "gamma": _u8f8(data, offset + 12)}
    values = [_u16(data, offset + 12 + i * 2) / 65535.0 for i in range(count)]
    return {"type": "curv", "count": count, "values": values}


def _parse_para(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    func_type = _u16(data, offset + 8)
    param_counts = {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}
    count = param_counts.get(func_type, 0)
    params = [_s15f16(data, offset + 12 + i * 4) for i in range(count)]
    return {"type": "para", "function_type": func_type, "params": params}


def decode_icc(icc_source: bytes | str | Path) -> Dict[str, Any]:
    data, file_name = _read_icc_bytes(icc_source)
    result = {"file_name": file_name}

    tag_count = _u32(data, 128)
    result["tag_count"] = tag_count
    result["tag_data"] = {}

    for i in range(tag_count):
        off = 132 + i * 12
        sig = _ascii(data, off, 4)
        data_off = _u32(data, off + 4)
        data_size = _u32(data, off + 8)
        tag_type = data[data_off : data_off + 4]

        if tag_type == b"curv":
            result["tag_data"][sig] = _parse_curv(data, data_off, data_size)
        elif tag_type == b"para":
            result["tag_data"][sig] = _parse_para(data, data_off, data_size)
        else:
            result["tag_data"][sig] = None  # ignore other types

    return result


def _linearize_array_with_icc_para(trc_dict, img_array):
    if trc_dict.get("type") != "para":
        raise ValueError("function only handles type 'para'")
    func_type = trc_dict["function_type"]
    params = trc_dict["params"]
    X = np.asarray(img_array, dtype=np.float32)

    if func_type == 0:
        return np.power(np.maximum(X, 0), params[0])
    elif func_type == 1:
        g, a, b = params[:3]
        base = a * X + b
        return np.where(base >= 0, np.power(np.maximum(base, 0), g), 0.0)
    elif func_type == 2:
        g, a, b, c = params[:4]
        base = a * X + b
        return np.where(base >= 0, np.power(np.maximum(base, 0), g) + c, c)
    elif func_type == 3:
        g, a, b, c, d = params[:5]
        return np.where(X >= d, np.power(np.maximum(a * X + b, 0), g), c * X)
    elif func_type == 4:
        g, a, b, c, d, e, f = params[:7]
        return np.where(X >= d, np.power(np.maximum(a * X + b, 0), g) + e, c * X + f)
    else:
        raise ValueError(f"unsupported function_type: {func_type}")


def _linearize_array_with_icc_curv(trc_dict, img_array):
    if trc_dict.get("type") != "curv":
        raise ValueError("function only handles type 'curv'")
    count = trc_dict["count"]
    X = np.asarray(img_array, dtype=np.float32)

    if count == 0:
        return X
    elif count == 1:
        return np.power(np.maximum(X, 0), trc_dict["gamma"])
    else:
        values = trc_dict["values"]
        xp = np.linspace(0.0, 1.0, count)
        yp = np.array(values, dtype=np.float32)
        return np.interp(X, xp, yp)


def linearize_array_with_icc(
    icc_file: bytes | str | Path, img_array: np.ndarray
) -> np.ndarray:
    result = decode_icc(icc_file)
    rtrc = result["tag_data"].get("rTRC")
    gtrc = result["tag_data"].get("gTRC")
    btrc = result["tag_data"].get("bTRC")
    trcs = [rtrc, gtrc, btrc]
    for trc in trcs:
        if trc is None:
            raise ValueError("tag not found in ICC profile")
        if trc.get("type") == "para":
            return _linearize_array_with_icc_para(trc, img_array)
        elif trc.get("type") == "curv":
            return _linearize_array_with_icc_curv(trc, img_array)
        else:
            raise ValueError("unsupported TRC type")
