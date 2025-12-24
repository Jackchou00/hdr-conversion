from __future__ import annotations
from hdrconv.core import GainmapImage


import io
import struct
import warnings
from fractions import Fraction
from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np
from PIL import Image

# -----------------------------------------------------------------------------
# Constants & Markers
# -----------------------------------------------------------------------------

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"
SOS = 0xFFDA
APP2 = 0xFFE2
ICC_PROFILE_LABEL = b"ICC_PROFILE\x00"
MPF_LABEL = b"MPF\x00"
# ISO 21496-1 Signature in APP2
ISO21496_URN = b"urn:iso:std:iso:ts:21496:-1\x00"
ISO21496_URN_ALT = b"urn:iso:std:iso:ts:21496:-1"  # Some writers omit null

# -----------------------------------------------------------------------------
# Helper: JPEG Segment Parsing
# -----------------------------------------------------------------------------


def _yield_jpeg_segments(data: bytes) -> Generator[Tuple[int, bytes], None, None]:
    """
    Yields (marker_code, payload) for segments before the image scan (SOS).
    """
    if data[:2] != SOI:
        return

    pos = 2
    length = len(data)

    while pos < length - 1:
        # Find next marker 0xFF
        if data[pos] != 0xFF:
            pos += 1
            continue

        marker = data[pos + 1]
        pos += 2

        # Skip padding 0xFF
        while marker == 0xFF and pos < length:
            marker = data[pos]
            pos += 1

        marker_code = 0xFF00 | marker

        # Standalone markers (no payload)
        if marker_code == SOS:
            yield marker_code, b""
            break  # Stop scanning at SOS to save time
        if marker_code == 0xFFD9:  # EOI
            break
        if 0xFFD0 <= marker_code <= 0xFFD7 or marker_code == 0xFF01:  # RSTn or TEM
            continue

        # Markers with payload
        if pos + 2 > length:
            break
        seg_len = int.from_bytes(data[pos : pos + 2], "big")
        # seg_len includes the 2 bytes for length itself
        payload_start = pos + 2
        payload_end = pos + seg_len

        if payload_end > length:
            break

        yield marker_code, data[payload_start:payload_end]
        pos = payload_end


# -----------------------------------------------------------------------------
# Helper: ICC & MPF Extraction
# -----------------------------------------------------------------------------


def _extract_icc(segments: List[Tuple[int, bytes]]) -> Optional[bytes]:
    """Combines split ICC chunks from APP2 segments."""
    chunks = {}
    expected_total = None

    for code, payload in segments:
        if code == APP2 and payload.startswith(ICC_PROFILE_LABEL):
            # Format: ID(12) + seq(1) + total(1) + data...
            if len(payload) < 14:
                continue
            seq = payload[12]
            total = payload[13]

            # Validate total consistency
            if expected_total is None:
                expected_total = total
            elif expected_total != total:
                # Inconsistent total values - file may be corrupted
                continue

            chunks[seq] = payload[14:]

    if not chunks:
        return None

    # Validate completeness (optional - warns but doesn't fail)
    if expected_total and len(chunks) != expected_total:
        # Missing chunks - assemble what we have but it may be incomplete
        pass

    # Assemble in order
    return b"".join(chunks[i] for i in sorted(chunks.keys()))


def _find_mpf_gainmap_offset(segments: List[Tuple[int, bytes]], file_len: int) -> int:
    """
    Parses MPF APP2 to find the offset of the second image (Gainmap).
    Returns 0 if not found.
    """
    for code, payload in segments:
        if code == APP2 and payload.startswith(MPF_LABEL):
            # Simplified MPF parser focusing on the Index IFD
            # Header: 'MPF\0' (4) + Endian(2) + 0x002A(2) + OffsetIFD(4)
            if len(payload) < 8:
                continue

            endian_sig = payload[4:6]
            endian = ">" if endian_sig == b"MM" else "<"

            try:
                first_ifd_offset = struct.unpack(f"{endian}I", payload[8:12])[0]
                # Jump to First IFD (Index IFD)
                # MPF Structure relative to the "MM/II" start (index 4 in payload)
                base = 4
                ifd_pos = base + first_ifd_offset
                num_entries = struct.unpack(
                    f"{endian}H", payload[ifd_pos : ifd_pos + 2]
                )[0]

                # Iterate MPF tags to find MP Entry tag (0xB002)
                entry_cursor = ifd_pos + 2
                mp_entries_data = None

                for _ in range(num_entries):
                    tag, typ, cnt, val_off = struct.unpack(
                        f"{endian}HHII", payload[entry_cursor : entry_cursor + 12]
                    )
                    if tag == 0xB002:  # MP Entry Tag
                        # Value is offset to the MP Entry list
                        data_off = base + val_off
                        # Each entry is 16 bytes
                        mp_entries_data = payload[data_off : data_off + (cnt * 16)]
                        break
                    entry_cursor += 12

                if mp_entries_data and len(mp_entries_data) >= 32:
                    # Look at second entry (Index 1) for the gainmap
                    # Entry structure: Attr(4), Size(4), Offset(4), Dep1(2), Dep2(2)
                    # Offset is relative to the MPF header start in the file.
                    # Usually, MPF header start = current_segment_offset + 4 + 4 (marker+len+MPF_sig...)
                    # Ideally, we calculate relative to file start if possible, but standard says relative to MPF header.

                    # Entry 2 starts at byte 16
                    e2_offset_val = struct.unpack(f"{endian}I", mp_entries_data[24:28])[
                        0
                    ]
                    if e2_offset_val > 0:
                        # We need the absolute file position.
                        # This implementation assumes standard construction where we can't easily get the absolute
                        # pos of the segment without tracking it.
                        # However, for decoding, we split the bytes.
                        # Note: This simple parser assumes the MPF logic implies encoded_iso21496 style structure.
                        # A robust one would track `pos` in the scanner.
                        pass

            except Exception:
                pass

    # Fallback: Many MPF implementations simply concatenate.
    # If we want to be precise, we need the segment offset.
    # Let's rely on a simpler heuristic for this utility:
    # The MPF offset is relative to the MPF Header (Start of 'MM'/'II').
    # We will return the extracted relative offset if found, but caller needs context.

    # RE-IMPLEMENTATION WITH OFFSET TRACKING
    # To correctly handle MPF, we need to scan the raw bytes again or return offsets from scanner.
    return 0


def _split_mpf_container(data: bytes) -> Tuple[bytes, bytes]:
    """
    Splits a JPEG file into (Primary, Gainmap) based on MPF or simple search.
    """
    # 1. Scan for MPF Segment
    pos = 0
    mpf_offset_base = 0
    second_image_offset = 0

    while pos < len(data) - 1:
        if data[pos : pos + 2] == b"\xff\xe2":  # APP2
            seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
            payload = data[pos + 4 : pos + 2 + seg_len]
            if payload.startswith(MPF_LABEL):
                # Found MPF
                mpf_offset_base = (
                    pos + 4 + 4
                )  # Start of Endian tag (after marker+len+MPF\0)
                endian = ">" if payload[4:6] == b"MM" else "<"
                try:
                    # Parse MP Entry for Image 2
                    first_ifd = struct.unpack(f"{endian}I", payload[8:12])[0]
                    base = 4
                    ifd_idx = base + first_ifd
                    entries_offset_local = 0

                    # Find tag 0xB002
                    cnt = struct.unpack(f"{endian}H", payload[ifd_idx : ifd_idx + 2])[0]
                    cursor = ifd_idx + 2
                    for _ in range(cnt):
                        tag, _, _, val = struct.unpack(
                            f"{endian}HHII", payload[cursor : cursor + 12]
                        )
                        if tag == 0xB002:
                            entries_offset_local = val
                            break
                        cursor += 12

                    if entries_offset_local:
                        # Get 2nd entry offset
                        # Entry 1 (16 bytes), Entry 2 (16 bytes)
                        entry2_pos = base + entries_offset_local + 16
                        img2_offset = struct.unpack(
                            f"{endian}I", payload[entry2_pos + 8 : entry2_pos + 12]
                        )[0]
                        if img2_offset > 0:
                            second_image_offset = mpf_offset_base + img2_offset
                except Exception:
                    pass
                break
            pos += 2 + seg_len
        elif data[pos] == 0xFF:
            # Fast forward
            pos += 1
        else:
            pos += 1

    if second_image_offset > 0 and second_image_offset < len(data):
        return data[:second_image_offset], data[second_image_offset:]

    # Fallback: Return only primary if split fails
    return data, b""


# -----------------------------------------------------------------------------
# ISO 21496-1 Logic
# -----------------------------------------------------------------------------


def _read_rational(data: bytes, offset: int, signed: bool = False) -> float:
    fmt = ">iI" if signed else ">II"
    num, den = struct.unpack_from(fmt, data, offset)
    return num / den if den != 0 else 0.0


def _parse_iso21496_metadata(payload: bytes) -> Dict[str, Any]:
    """Parses binary APP2 payload into the specified dictionary structure."""

    # Skip URN
    offset = 0
    if payload.startswith(ISO21496_URN):
        offset = len(ISO21496_URN)
    elif payload.startswith(ISO21496_URN_ALT):
        offset = len(ISO21496_URN_ALT)
    else:
        raise ValueError("Invalid ISO 21496 signature")

    # Header
    min_ver, writer_ver, flags = struct.unpack_from(">HHB", payload, offset)
    offset += 5

    is_multichannel = bool((flags >> 7) & 1)
    use_base_space = bool((flags >> 6) & 1)

    # Headroom
    base_headroom = _read_rational(payload, offset, False)
    offset += 8
    alt_headroom = _read_rational(payload, offset, False)
    offset += 8

    # Channels
    channel_count = 3 if is_multichannel else 1
    channels = []

    for _ in range(channel_count):
        c = {}
        c["min"] = _read_rational(payload, offset, True)
        offset += 8
        c["max"] = _read_rational(payload, offset, True)
        offset += 8
        c["gamma"] = _read_rational(payload, offset, False)
        offset += 8
        c["base_off"] = _read_rational(payload, offset, True)
        offset += 8
        c["alt_off"] = _read_rational(payload, offset, True)
        offset += 8
        channels.append(c)

    # Format to Output Structure
    def get_triple(key):
        if is_multichannel:
            return (channels[0][key], channels[1][key], channels[2][key])
        else:
            v = channels[0][key]
            return (v, v, v)

    return {
        "alternate_hdr_headroom": float(alt_headroom),
        "baseline_hdr_headroom": float(base_headroom),
        "is_multichannel": is_multichannel,
        "use_base_colour_space": use_base_space,
        "minimum_version": min_ver,  # Should be 0
        "writer_version": writer_ver,
        "alternate_offset": get_triple("alt_off"),
        "baseline_offset": get_triple("base_off"),
        "gainmap_min": get_triple("min"),
        "gainmap_max": get_triple("max"),
        "gainmap_gamma": get_triple("gamma"),
    }


def _encode_iso21496_metadata(meta: Dict[str, Any]) -> bytes:
    """Encodes the metadata dict into binary APP2 payload."""

    def to_rational(val: float, signed: bool) -> Tuple[int, int]:
        f = Fraction(val).limit_denominator(100000)
        num, den = f.numerator, f.denominator
        if signed:
            num = max(-(2**31), min(2**31 - 1, num))
            den = max(1, min(2**32 - 1, den))
        else:
            num = max(0, min(2**32 - 1, num))
            den = max(1, min(2**32 - 1, den))
        return int(num), int(den)

    out = bytearray()
    out.extend(ISO21496_URN)

    min_ver = meta.get("minimum_version", 0)
    wri_ver = meta.get("writer_version", 0)
    is_mc = meta.get("is_multichannel", False)
    use_base = meta.get("use_base_colour_space", False)

    flags = (1 if is_mc else 0) << 7 | (1 if use_base else 0) << 6
    out.extend(struct.pack(">HHB", min_ver, wri_ver, flags))

    # Headroom
    n, d = to_rational(meta.get("baseline_hdr_headroom", 0.0), False)
    out.extend(struct.pack(">II", n, d))
    n, d = to_rational(meta.get("alternate_hdr_headroom", 0.0), False)
    out.extend(struct.pack(">II", n, d))

    # Channels
    count = 3 if is_mc else 1

    gm_min = meta.get("gainmap_min", (0, 0, 0))
    gm_max = meta.get("gainmap_max", (1, 1, 1))
    gm_gam = meta.get("gainmap_gamma", (1, 1, 1))
    base_off = meta.get("baseline_offset", (0, 0, 0))
    alt_off = meta.get("alternate_offset", (0, 0, 0))

    for i in range(count):
        # min (signed)
        n, d = to_rational(gm_min[i], True)
        out.extend(struct.pack(">iI", n, d))
        # max (signed)
        n, d = to_rational(gm_max[i], True)
        out.extend(struct.pack(">iI", n, d))
        # gamma (unsigned)
        n, d = to_rational(gm_gam[i], False)
        out.extend(struct.pack(">II", n, d))
        # base offset (signed)
        n, d = to_rational(base_off[i], True)
        out.extend(struct.pack(">iI", n, d))
        # alt offset (signed)
        n, d = to_rational(alt_off[i], True)
        out.extend(struct.pack(">iI", n, d))

    return bytes(out)


# -----------------------------------------------------------------------------
# Encoding Helpers
# -----------------------------------------------------------------------------


def _create_jpeg_bytes(img_arr: np.ndarray, icc: bytes | None) -> bytes:
    """使用 PIL 将 numpy 数组编码为 JPEG 字节流"""
    # 数据类型转换与校验
    if img_arr.dtype != np.uint8:
        if np.issubdtype(img_arr.dtype, np.floating):
            img_arr = np.clip(img_arr * 255, 0, 255).astype(np.uint8)
        else:
            img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)

    # 确保是 RGB
    if img_arr.ndim == 2:
        img_arr = np.stack([img_arr] * 3, axis=-1)
    elif img_arr.shape[2] == 4:
        img_arr = img_arr[:, :, :3]  # 丢弃 Alpha

    pil_img = Image.fromarray(img_arr)
    bio = io.BytesIO()

    save_kwargs = {
        "format": "JPEG",
        "quality": 95,
        "subsampling": 0,  # 4:4:4 采样以获得更好质量
    }
    if icc:
        save_kwargs["icc_profile"] = icc

    pil_img.save(bio, **save_kwargs)
    return bio.getvalue()


def _build_app2_segment(payload: bytes) -> bytes:
    """封装 JPEG APP2 段标记"""
    # Marker (FF E2) + Length (2 bytes) + Payload
    length = len(payload) + 2
    return b"\xff\xe2" + length.to_bytes(2, "big") + payload


def _build_mpf_payload(
    primary_size: int, gainmap_size: int, gainmap_offset: int
) -> bytes:
    """
    构建 MPF (Multi-Picture Format) 的二进制 Payload。
    包含2个图像条目：Index 0 (Primary), Index 1 (Gainmap)。
    """
    # MPF 签名
    mpf_sig = b"MPF\x00"
    # Endianness (Big Endian)
    byte_order = b"MM"

    # --- 构建 MP Entry List (图像索引表) ---
    # 每个条目 16 字节: Attribute(4), Size(4), Offset(4), Dependent(2+2)
    entries = bytearray()

    # Entry 0: Primary Image
    # Attribute: 0x030000 (Baseline MP Primary Image)
    entries.extend(struct.pack(">I", 0x030000))
    entries.extend(struct.pack(">I", primary_size))
    entries.extend(struct.pack(">I", 0))  # Offset 0 (本身)
    entries.extend(struct.pack(">I", 0))  # Dep entries (0)

    # Entry 1: Gainmap Image
    # Attribute: 0x050000 (Large Thumbnail / Undefined / Gainmap role)
    entries.extend(struct.pack(">I", 0x050000))
    entries.extend(struct.pack(">I", gainmap_size))
    entries.extend(struct.pack(">I", gainmap_offset))
    entries.extend(struct.pack(">I", 0))

    # --- 构建 Index IFD ---
    # 包含3个标签: Version, NumberOfImages, MPEntry
    num_tags = 3
    ifd = bytearray()

    # Tag 1: MPF Version (0xB000)
    ifd.extend(struct.pack(">H", 0xB000))
    ifd.extend(struct.pack(">H", 7))  # Type: UNDEFINED
    ifd.extend(struct.pack(">I", 4))  # Count: 4
    ifd.extend(b"0100")  # Value: "0100"

    # Tag 2: Number of Images (0xB001)
    ifd.extend(struct.pack(">H", 0xB001))
    ifd.extend(struct.pack(">H", 4))  # Type: LONG
    ifd.extend(struct.pack(">I", 1))  # Count: 1
    ifd.extend(struct.pack(">I", 2))  # Value: 2 images

    # Tag 3: MP Entry (0xB002)
    ifd.extend(struct.pack(">H", 0xB002))
    ifd.extend(struct.pack(">H", 7))  # Type: UNDEFINED
    ifd.extend(struct.pack(">I", 32))  # Count: 16 bytes * 2 entries = 32
    # Offset to Data:
    #   Header(8) + IFD_Count(2) + Tags(3*12=36) + NextIFD(4) = 50 字节
    ifd.extend(struct.pack(">I", 50))

    # --- 组装所有部分 ---
    payload = bytearray()
    payload.extend(mpf_sig)  # 4 bytes
    payload.extend(byte_order)  # 2 bytes
    payload.extend(b"\x00\x2a")  # 2 bytes (0x002A)
    payload.extend(struct.pack(">I", 8))  # Offset to First IFD (8 bytes from 'MM')

    # IFD Block
    payload.extend(struct.pack(">H", num_tags))
    payload.extend(ifd)
    payload.extend(struct.pack(">I", 0))  # Next IFD Offset (0 = None)

    # Data Area (Entries)
    payload.extend(entries)

    return bytes(payload)


def _build_mpf_minimal_payload(num_images: int) -> bytes:
    """构建最小 MPF payload（仅包含 Version + NumberOfImages）。

    一些兼容性实现会期望 gainmap 流中也存在一个最小 MPF APP2。
    """
    mpf_sig = b"MPF\x00"
    byte_order = b"MM"

    num_tags = 2
    ifd = bytearray()

    # MPF Version (0xB000)
    ifd.extend(struct.pack(">H", 0xB000))
    ifd.extend(struct.pack(">H", 7))
    ifd.extend(struct.pack(">I", 4))
    ifd.extend(b"0100")

    # Number of Images (0xB001)
    ifd.extend(struct.pack(">H", 0xB001))
    ifd.extend(struct.pack(">H", 4))
    ifd.extend(struct.pack(">I", 1))
    ifd.extend(struct.pack(">I", int(num_images)))

    payload = bytearray()
    payload.extend(mpf_sig)
    payload.extend(byte_order)
    payload.extend(b"\x00\x2a")
    payload.extend(struct.pack(">I", 8))
    payload.extend(struct.pack(">H", num_tags))
    payload.extend(ifd)
    payload.extend(struct.pack(">I", 0))
    return bytes(payload)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def read_21496(filepath: str) -> GainmapImage:
    """
    Read ISO 21496-1 Gainmap JPEG file.

    Args:
        filepath: Path to the ISO 21496-1 JPEG file

    Returns:
        GainmapImage dict containing:
        - baseline: uint8 array (H, W, 3), range [0, 255]
        - gainmap: uint8 array (H, W, 3) or (H, W, 1), range [0, 255]
        - metadata: ISO21496GainmapMetadata dict
        - baseline_icc: Optional ICC profile bytes
        - gainmap_icc: Optional ICC profile bytes
    """
    with open(filepath, "rb") as f:
        raw_data = f.read()

    # 1. Split streams (Primary vs Gainmap) via MPF
    primary_data, gainmap_data = _split_mpf_container(raw_data)

    if not gainmap_data:
        raise ValueError("No gainmap found in container (MPF missing or invalid).")

    # 2. Decode Images
    # Suppress MPO-related warnings from Pillow when reading JPEG streams
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Image appears to be a malformed MPO file",
            category=UserWarning,
        )
        base_img = Image.open(io.BytesIO(primary_data)).convert("RGB")
        gain_img = Image.open(io.BytesIO(gainmap_data)).convert("RGB")

    base_arr = np.array(base_img)
    gain_arr = np.array(gain_img)

    # 3. Extract Metadata & ICC
    # Metadata usually lives in the Gainmap stream's APP2, but we check both.

    base_segments = list(_yield_jpeg_segments(primary_data))
    gain_segments = list(_yield_jpeg_segments(gainmap_data))

    base_icc = _extract_icc(base_segments)
    gain_icc = _extract_icc(gain_segments)

    iso_meta = None

    # Search for ISO 21496 metadata (Prioritize Gainmap stream)
    for segments in [gain_segments, base_segments]:
        for code, payload in segments:
            if code == APP2 and (
                payload.startswith(ISO21496_URN) or payload.startswith(ISO21496_URN_ALT)
            ):
                iso_meta = _parse_iso21496_metadata(payload)
                break
        if iso_meta:
            break

    if not iso_meta:
        raise ValueError("ISO 21496-1 metadata segment not found.")

    return GainmapImage(
        baseline=base_arr,
        gainmap=gain_arr,
        metadata=iso_meta,
        baseline_icc=base_icc,
        gainmap_icc=gain_icc,
    )


def write_21496(data: GainmapImage, filepath: str) -> None:
    """
    Write ISO 21496-1 Gainmap JPEG file.

    Args:
        data: GainmapImage dict with baseline, gainmap, and metadata
        filepath: Output path for the JPEG file
    """
    try:
        # 1. 编码 Gainmap 图像 (基础 JPEG 编码)
        gainmap_bytes_raw = _create_jpeg_bytes(data["gainmap"], data.get("gainmap_icc"))

        # 1.1 在 Gainmap 流中插入一个最小 MPF APP2（兼容性需要）
        gainmap_mpf_segment = _build_app2_segment(_build_mpf_minimal_payload(2))

        # 2. 构建 ISO 21496-1 元数据段 (APP2)
        #    标准建议将此元数据放在 Gainmap 图像流中
        iso_payload = _encode_iso21496_metadata(data["metadata"])
        iso_segment = _build_app2_segment(iso_payload)

        #    将 ISO 段插入到 Gainmap 的 SOI (0xFFD8) 之后
        gainmap_final = (
            gainmap_bytes_raw[:2]
            + gainmap_mpf_segment
            + iso_segment
            + gainmap_bytes_raw[2:]
        )

        # 3. 编码 Baseline 图像 (基础 JPEG 编码)
        primary_bytes_raw = _create_jpeg_bytes(
            data["baseline"], data.get("baseline_icc")
        )

        # 3.1 在 Primary 流中插入一个短 URN stub APP2（兼容性需要）
        # 该 stub 不是完整元数据，仅用于标记 ISO21496 容器。
        primary_stub_segment = _build_app2_segment(ISO21496_URN + b"\x00\x00\x00\x00")

        # 4. 构建 MPF 索引段 (APP2)
        #    MPF 位于 Baseline 图像中，用于指向文件末尾的 Gainmap

        #    A. 首先生成一个带有占位偏移量的 MPF payload，用于计算长度
        #       MPF 段放在 Primary stub 之后
        mpf_payload_temp = _build_mpf_payload(
            primary_size=len(primary_bytes_raw),  # 暂时的，稍后修正
            gainmap_size=len(gainmap_final),
            gainmap_offset=0,  # 占位
        )
        mpf_segment_temp = _build_app2_segment(mpf_payload_temp)

        #    B. 计算最终文件结构中的绝对位置
        #       Primary_Final_Len = Raw_Primary_Len + Stub_Seg_Len + MPF_Seg_Len
        total_primary_len = (
            len(primary_bytes_raw) + len(primary_stub_segment) + len(mpf_segment_temp)
        )

        #    C. 计算 Gainmap 的相对偏移量
        #       MPF 标准规定偏移量是相对于 MPF Header (即 'MM'/'II' 字节) 的位置
        #       base_file_offset = MPF marker 的文件偏移 + 8 (marker+len+"MPF\0")
        mpf_marker_offset = 2 + len(primary_stub_segment)
        mpf_base_file_offset = mpf_marker_offset + 8
        gainmap_relative_offset = total_primary_len - mpf_base_file_offset

        #    D. 重新生成包含正确 Primary 大小和 Gainmap 偏移量的 MPF payload
        mpf_payload_final = _build_mpf_payload(
            primary_size=total_primary_len,
            gainmap_size=len(gainmap_final),
            gainmap_offset=gainmap_relative_offset,
        )
        mpf_segment_final = _build_app2_segment(mpf_payload_final)

        # 5. 组装 Baseline 流 (插入 MPF)
        primary_final = (
            primary_bytes_raw[:2]
            + primary_stub_segment
            + mpf_segment_final
            + primary_bytes_raw[2:]
        )

        # 6. 拼接并写入文件 (Baseline + Gainmap)
        with open(filepath, "wb") as f:
            f.write(primary_final)
            f.write(gainmap_final)

    except Exception as e:
        raise RuntimeError(f"Failed to write ISO 21496-1 file: {filepath}") from e
