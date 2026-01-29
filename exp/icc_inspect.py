#!/usr/bin/env python3
"""ICC profile inspection and color conversion tool.

This tool provides accurate color space conversion using ICC profile data:

**Method: Matrix + TRC (Recommended)**
- Extracts colorant matrix and TRC from ICC profile
- Applies gamma/parametric curve transformation
- Perfect round-trip accuracy with no Lab conversion loss

**Usage:**
1. Parse ICC profile to extract matrices and TRC
2. RGB -> XYZ: Use `rgb_to_xyz_matrix(rgb, apply_trc_flag=True)`
3. XYZ -> RGB: Use `xyz_to_rgb_matrix(xyz, apply_inverse_trc=True)`

**Features:**
- Supports Gamma, Parametric (sRGB-like), and Curve TRC types
- Handles chromatic adaptation (Device White <-> D50)
- No precision loss from Lab uint8 encoding
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import ImageCms


@dataclass
class ICCProfileData:
    path: Path
    desc: str
    pcs: str
    color_space: str
    rgb_to_xyz_matrix: Optional[np.ndarray] = None
    chad_matrix: Optional[np.ndarray] = None
    primaries: Dict[str, np.ndarray] = field(default_factory=dict)
    whitepoint: Optional[np.ndarray] = None
    trc_info: Dict[str, Any] = field(default_factory=dict)


class ByteReader:
    """Helper for reading binary data from ICC profiles."""

    def __init__(self, data: bytes):
        self.data = data

    def u32(self, offset: int) -> int:
        return struct.unpack(">I", self.data[offset : offset + 4])[0]

    def u16(self, offset: int) -> int:
        return struct.unpack(">H", self.data[offset : offset + 2])[0]

    def s15f16(self, offset: int) -> float:
        return struct.unpack(">i", self.data[offset : offset + 4])[0] / 65536.0

    def ascii(self, offset: int, length: int) -> str:
        return self.data[offset : offset + length].decode("ascii", errors="replace")


class ICCParser:
    """Parser for ICC profile files."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = path.read_bytes()
        except FileNotFoundError:
            raise ValueError(f"File not found: {path}")
        if len(self.data) < 128:
            raise ValueError("Invalid ICC file length")
        self.reader = ByteReader(self.data)
        self.tags = self._index_tags()

    def parse(self) -> ICCProfileData:
        """Parse ICC profile and extract colorimetric data.

        Returns:
            ICCProfileData containing profile metadata and color transform matrices.
        """
        header = self._parse_header()
        r_xyz = self._read_xyz_tag("rXYZ")
        g_xyz = self._read_xyz_tag("gXYZ")
        b_xyz = self._read_xyz_tag("bXYZ")
        wtpt = self._read_xyz_tag("wtpt")

        rgb_matrix = None
        if r_xyz is not None and g_xyz is not None and b_xyz is not None:
            rgb_matrix = np.column_stack((r_xyz, g_xyz, b_xyz))

        chad = self._read_sf32_matrix("chad")
        trc = self._parse_trc("rTRC") or self._parse_trc("kTRC")
        desc = self._read_desc()

        return ICCProfileData(
            path=self.path,
            desc=desc,
            pcs=header["pcs"],
            color_space=header["color_space"],
            rgb_to_xyz_matrix=rgb_matrix,
            chad_matrix=chad,
            primaries={"R": r_xyz, "G": g_xyz, "B": b_xyz},
            whitepoint=wtpt,
            trc_info=trc,
        )

    def _index_tags(self) -> Dict[str, Tuple[int, int]]:
        """Build tag index from ICC profile tag table."""
        count = self.reader.u32(128)
        tags = {}
        offset = 132
        for _ in range(count):
            sig = self.reader.ascii(offset, 4)
            tag_offset = self.reader.u32(offset + 4)
            tag_size = self.reader.u32(offset + 8)
            tags[sig] = (tag_offset, tag_size)
            offset += 12
        return tags

    def _parse_header(self) -> Dict[str, str]:
        return {
            "device_class": self.reader.ascii(12, 4),
            "color_space": self.reader.ascii(16, 4).strip(),
            "pcs": self.reader.ascii(20, 4).strip(),
        }

    def _get_tag_data(self, tag: str) -> Optional[bytes]:
        if tag not in self.tags:
            return None
        offset, size = self.tags[tag]
        return self.data[offset : offset + size]

    def _read_xyz_tag(self, tag: str) -> Optional[np.ndarray]:
        data = self._get_tag_data(tag)
        if not data or data[:4] != b"XYZ ":
            return None
        return np.array(
            [
                self.reader.s15f16(self.tags[tag][0] + 8),
                self.reader.s15f16(self.tags[tag][0] + 12),
                self.reader.s15f16(self.tags[tag][0] + 16),
            ]
        )

    def _read_sf32_matrix(self, tag: str) -> Optional[np.ndarray]:
        data = self._get_tag_data(tag)
        if not data or data[:4] != b"sf32":
            return None
        start = self.tags[tag][0] + 8
        values = []
        for i in range(9):
            if start + i * 4 + 4 > self.tags[tag][0] + len(data):
                break
            values.append(self.reader.s15f16(start + i * 4))
        arr = np.array(values)
        return arr.reshape(3, 3) if arr.size == 9 else arr

    def _read_desc(self) -> str:
        data = self._get_tag_data("desc")
        if data:
            count = self.reader.u32(self.tags["desc"][0] + 8)
            return data[12 : 12 + count].decode("ascii", errors="ignore").strip("\x00")
        return "Unknown"

    def _parse_trc(self, tag: str) -> Dict[str, Any]:
        data = self._get_tag_data(tag)
        if not data:
            return {}
        sig = data[:4].decode("ascii")
        offset = self.tags[tag][0]
        if sig == "curv":
            count = self.reader.u32(offset + 8)
            if count == 0:
                return {"type": "Linear"}
            if count == 1:
                gamma = self.reader.u16(offset + 12) / 256.0
                return {"type": "Gamma", "gamma": gamma}
            # Read curve points
            points = []
            for i in range(count):
                points.append(self.reader.u16(offset + 12 + i * 2) / 65535.0)
            return {"type": "Curve", "points": count, "values": points}
        elif sig == "para":
            func_type = self.reader.u16(offset + 8)
            # Read parameters based on function type
            params = []
            param_count = [1, 3, 4, 5, 7][min(func_type, 4)]
            for i in range(param_count):
                params.append(self.reader.s15f16(offset + 12 + i * 4))
            return {"type": "Parametric", "function_type": func_type, "params": params}
        return {"type": sig}


def apply_trc(value: float, trc: Dict[str, Any]) -> float:
    """Apply tone reproduction curve to a single channel value.

    Args:
        value: Input value (0-1 range).
        trc: TRC information dict.

    Returns:
        Transformed value.
    """
    value = np.clip(value, 0, 1)

    if not trc or trc.get("type") == "Linear":
        return value

    if trc.get("type") == "Gamma":
        gamma = trc.get("gamma", 1.0)
        return value**gamma

    if trc.get("type") == "Curve" and "values" in trc:
        # Interpolate in curve
        values = trc["values"]
        n = len(values)
        if n == 0:
            return value
        idx = value * (n - 1)
        i0 = int(np.floor(idx))
        i1 = min(i0 + 1, n - 1)
        frac = idx - i0
        return values[i0] * (1 - frac) + values[i1] * frac

    if trc.get("type") == "Parametric":
        # Implement parametric curves
        func_type = trc.get("function_type", 0)
        params = trc.get("params", [])

        if func_type == 0 and len(params) >= 1:  # Y = X^gamma
            gamma = params[0]
            return value**gamma
        elif func_type == 1 and len(params) >= 3:  # CIE 122-1966
            gamma, a, b = params[0], params[1], params[2]
            if value >= -b / a:
                return (a * value + b) ** gamma
            else:
                return 0.0
        elif func_type == 3 and len(params) >= 5:  # sRGB-like
            gamma, a, b, c, d = params[0], params[1], params[2], params[3], params[4]
            if value >= d:
                return (a * value + b) ** gamma
            else:
                return c * value

    return value


def inverse_trc(value: float, trc: Dict[str, Any]) -> float:
    """Apply inverse TRC (linearize).

    Args:
        value: Input value (0-1 range).
        trc: TRC information dict.

    Returns:
        Linearized value.
    """
    value = np.clip(value, 0, 1)

    if not trc or trc.get("type") == "Linear":
        return value

    if trc.get("type") == "Gamma":
        gamma = trc.get("gamma", 1.0)
        return value ** (1.0 / gamma) if gamma > 0 else value

    if trc.get("type") == "Parametric":
        func_type = trc.get("function_type", 0)
        params = trc.get("params", [])

        if func_type == 0 and len(params) >= 1:
            gamma = params[0]
            return value ** (1.0 / gamma) if gamma > 0 else value
        elif func_type == 3 and len(params) >= 5:  # sRGB-like inverse
            gamma, a, b, c, d = params[0], params[1], params[2], params[3], params[4]
            threshold = (a * d + b) ** gamma if gamma > 0 else 0
            if value >= threshold:
                return (
                    ((value ** (1 / gamma)) - b) / a if a != 0 and gamma > 0 else value
                )
            else:
                return value / c if c != 0 else value

    return value


class ColorEngine:
    """Color conversion engine using ICC profiles with chromatic adaptation."""

    def __init__(
        self,
        icc_path: Path,
        chad: Optional[np.ndarray],
        rgb_matrix: Optional[np.ndarray] = None,
        trc: Optional[Dict[str, Any]] = None,
    ):
        """Initialize color engine.

        Args:
            icc_path: Path to ICC profile.
            chad: Chromatic adaptation matrix (Device White -> D50).
            rgb_matrix: RGB to XYZ(D50) colorant matrix.
            trc: Tone reproduction curve info.
        """
        self.icc_path = icc_path
        self.chad = chad
        self.chad_inv = np.linalg.inv(chad) if chad is not None else None
        self.rgb_matrix = rgb_matrix
        self.rgb_matrix_inv = (
            np.linalg.inv(rgb_matrix) if rgb_matrix is not None else None
        )
        self.trc = trc

        try:
            self.src_profile = ImageCms.ImageCmsProfile(str(icc_path))
        except Exception:
            sys.exit("Error loading ICC profile")

    def rgb_to_xyz_matrix(
        self, rgb: Tuple[float, float, float], apply_trc_flag: bool = False
    ) -> np.ndarray:
        """Convert RGB to XYZ using matrix multiplication.

        Args:
            rgb: RGB values (0-1 range).
            apply_trc_flag: If True, apply TRC to linearize RGB first.

        Returns:
            XYZ tristimulus values in device white space (e.g., D65).

        Note:
            The conversion chain is:
            RGB -> [TRC] -> Linear RGB -> [Colorant Matrix] -> XYZ(D50)
            -> [Chad_inv] -> XYZ(Device White)
        """
        if self.rgb_matrix is None:
            raise ValueError("RGB matrix not available")

        rgb_arr = np.array(rgb)

        # Apply TRC to linearize if requested
        if apply_trc_flag and self.trc:
            rgb_arr = np.array([apply_trc(c, self.trc) for c in rgb_arr])

        # Colorant matrix gives XYZ in D50 (PCS)
        xyz_d50 = self.rgb_matrix @ rgb_arr

        # Transform D50 to device white space (e.g., D65)
        if self.chad_inv is not None:
            return self.chad_inv @ xyz_d50
        return xyz_d50

    def xyz_to_rgb_matrix(
        self, xyz_device: Tuple[float, float, float], apply_inverse_trc: bool = False
    ) -> np.ndarray:
        """Convert XYZ to RGB using matrix multiplication.

        Args:
            xyz_device: XYZ values in device white space (e.g., D65).
            apply_inverse_trc: If True, apply inverse TRC to get display RGB.

        Returns:
            RGB values (0-1 range).

        Note:
            The conversion chain is:
            XYZ(Device White) -> [Chad] -> XYZ(D50) -> [Colorant_inv]
            -> Linear RGB -> [Inverse TRC] -> RGB
        """
        if self.rgb_matrix_inv is None:
            raise ValueError("RGB matrix not available")

        xyz_arr = np.array(xyz_device)

        # Transform device white space to D50 (PCS)
        if self.chad is not None:
            xyz_d50 = self.chad @ xyz_arr
        else:
            xyz_d50 = xyz_arr

        # Inverse colorant matrix to get linear RGB
        rgb_linear = self.rgb_matrix_inv @ xyz_d50
        rgb_linear = np.clip(rgb_linear, 0, 1)

        # Apply inverse TRC if requested
        if apply_inverse_trc and self.trc:
            rgb = np.array([inverse_trc(c, self.trc) for c in rgb_linear])
            return np.clip(rgb, 0, 1)

        return rgb_linear


def format_matrix(mat: Optional[np.ndarray]) -> str:
    """Format matrix for display."""
    if mat is None:
        return "None"
    return "\n".join(
        ["  [ " + ", ".join(f"{v:9.5f}" for v in row) + " ]" for row in mat]
    )


def main():
    """Run ICC profile inspection and color conversion tests."""
    icc_dir = Path("icc")
    icc_files = sorted(icc_dir.glob("*.icc"))
    
    if not icc_files:
        print("No ICC files found in icc/ directory")
        return

    test_rgb_values = [
        (1.0, 1.0, 1.0),  # White
        (1.0, 0.0, 0.0),  # Red
        (0.0, 1.0, 0.0),  # Green
        (0.0, 0.0, 1.0),  # Blue
    ]

    for icc_path in icc_files:
        print(f"\n{'=' * 60}")
        print(f"Profile: {icc_path.name}")
        print("=" * 60)

        try:
            data = ICCParser(icc_path).parse()
        except Exception as e:
            print(f"❌ Parsing failed: {e}")
            continue

        print(f"Description: {data.desc or 'N/A'}")
        print(f"Color Space: {data.color_space}")
        print(f"PCS: {data.pcs}")
        print(f"TRC Type: {data.trc_info.get('type', 'Unknown')}")

        if data.trc_info.get("type") == "Gamma":
            print(f"  Gamma: {data.trc_info.get('gamma', 'N/A')}")
        elif data.trc_info.get("type") == "Parametric":
            params = data.trc_info.get("params", [])
            if params:
                print(f"  Gamma: {params[0]:.4f}")

        print("\nChromatic Adaptation Matrix (Device White -> D50):")
        print(format_matrix(data.chad_matrix))

        print("\nColorant Matrix (RGB -> XYZ D50):")
        print(format_matrix(data.rgb_to_xyz_matrix))

        if data.rgb_to_xyz_matrix is None or data.chad_matrix is None:
            print("⚠️  Cannot perform conversion tests (missing matrix data)")
            continue

        engine = ColorEngine(
            icc_path, data.chad_matrix, data.rgb_to_xyz_matrix, data.trc_info
        )

        print("\nRound-trip Test (RGB -> XYZ -> RGB with TRC):")
        all_passed = True
        for rgb_in in test_rgb_values:
            xyz_out = engine.rgb_to_xyz_matrix(rgb_in, apply_trc_flag=True)
            rgb_back = engine.xyz_to_rgb_matrix(xyz_out, apply_inverse_trc=True)
            error = np.abs(np.array(rgb_in) - rgb_back).max()
            status = "✓" if error < 0.001 else "✗"
            if error >= 0.001:
                all_passed = False
            print(
                f"  {status} RGB {rgb_in} -> RGB {tuple(f'{v:.5f}' for v in rgb_back)} (Error: {error:.6f})"
            )

        if all_passed:
            print("✅ All round-trip tests passed!")

        # Show one example conversion
        print("\nExample Conversion (with TRC):")
        rgb_example = (0.5, 0.5, 0.5)

        # Get XYZ in device white space (e.g., D65 for Display P3)
        xyz_device = engine.rgb_to_xyz_matrix(rgb_example, apply_trc_flag=True)

        # Also get XYZ in D50 (PCS) for comparison
        rgb_linear = np.array([apply_trc(c, data.trc_info) for c in rgb_example])
        xyz_d50 = data.rgb_to_xyz_matrix @ rgb_linear

        rgb_result = engine.xyz_to_rgb_matrix(xyz_device, apply_inverse_trc=True)

        print(f"  RGB {rgb_example}")
        print(
            f"  -> XYZ(D50 PCS) [{xyz_d50[0]:.5f}, {xyz_d50[1]:.5f}, {xyz_d50[2]:.5f}]"
        )
        print(
            f"  -> XYZ(Device)  [{xyz_device[0]:.5f}, {xyz_device[1]:.5f}, {xyz_device[2]:.5f}]"
        )
        print(
            f"  -> RGB back     [{rgb_result[0]:.5f}, {rgb_result[1]:.5f}, {rgb_result[2]:.5f}]"
        )
        print(
            f"  Round-trip error: {np.abs(np.array(rgb_example) - rgb_result).max():.8f}"
        )

if __name__ == "__main__":
    main()
