import struct
from pathlib import Path

import numpy as np
import pytest
from imagecodecs import avif_encode

from hdrconv.io.iso22028 import read_22028_pq, write_22028_pq

IMAGES_DIR = Path(__file__).resolve().parents[1] / "images"


def _encode_avif(array, bits, primaries=9):
    return avif_encode(
        array,
        level=90,
        speed=8,
        bitspersample=bits,
        primaries=primaries,
        transfer=16,
        numthreads=-1,
    )


def _parse_nclx(avif_bytes):
    idx = avif_bytes.find(b"colrnclx")
    assert idx >= 0, "no nclx colr box found"
    return struct.unpack(">HHH", avif_bytes[idx + 8 : idx + 14])


@pytest.mark.parametrize("bits", [8, 10, 12])
def test_read_scales_white_by_actual_bit_depth(tmp_path, bits):
    max_code = (1 << bits) - 1
    dtype = np.uint8 if bits == 8 else np.uint16
    array = np.full((16, 16, 3), max_code, dtype=dtype)
    path = tmp_path / f"white_{bits}.avif"
    path.write_bytes(_encode_avif(array, bits))

    img = read_22028_pq(str(path))

    assert img["data"].dtype == np.float32
    assert img["data"].max() == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize(
    "primaries,expected",
    [(1, "bt709"), (12, "p3"), (9, "bt2020")],
)
def test_read_parses_nclx_primaries(tmp_path, primaries, expected):
    array = np.full((8, 8, 3), 512, dtype=np.uint16)
    path = tmp_path / f"primaries_{primaries}.avif"
    path.write_bytes(_encode_avif(array, 10, primaries=primaries))

    img = read_22028_pq(str(path))

    assert img["color_space"] == expected


@pytest.mark.skipif(
    not (IMAGES_DIR / "iso22028.avif").exists(),
    reason="sample images directory not available",
)
def test_read_sample_file():
    img = read_22028_pq(str(IMAGES_DIR / "iso22028.avif"))
    # 10-bit sample file: values unchanged by the bit-depth parsing.
    assert img["data"].dtype == np.float32
    assert img["data"].max() == pytest.approx(813 / 1023, abs=1e-6)
    assert img["color_space"] == "bt2020"
    assert img["transfer_function"] == "pq"


def test_write_defaults_missing_color_space_and_tags_cicp(tmp_path):
    data = {
        "data": np.full((8, 8, 3), 0.5, dtype=np.float32),
        "transfer_function": "pq",
    }
    path = tmp_path / "out.avif"
    write_22028_pq(data, str(path))  # must not raise KeyError

    primaries, transfer, matrix = _parse_nclx(path.read_bytes())
    assert (primaries, transfer, matrix) == (9, 16, 9)


def test_write_rounds_quantization(tmp_path, monkeypatch):
    captured = {}

    def fake_encode(array, **kwargs):
        captured["array"] = array
        return b"avif"

    monkeypatch.setattr("hdrconv.io.iso22028.avif_encode", fake_encode)
    # 0.2 * 1023 = 204.6 -> must round to 205, not truncate to 204.
    data = {
        "data": np.full((4, 4, 3), 0.2, dtype=np.float32),
        "transfer_function": "pq",
        "color_space": "bt2020",
    }
    write_22028_pq(data, str(tmp_path / "out.avif"))

    assert captured["array"].dtype == np.uint16
    assert int(captured["array"][0, 0, 0]) == 205


def test_write_read_roundtrip(tmp_path):
    # Smooth gradient: representative content for a lossy codec.
    gradient = np.linspace(0.0, 1.0, 64, dtype=np.float32)
    original = np.stack(
        [
            np.tile(gradient, (64, 1)),
            np.tile(gradient[:, None], (1, 64)),
            np.full((64, 64), 0.5, dtype=np.float32),
        ],
        axis=-1,
    )
    data = {
        "data": original,
        "transfer_function": "pq",
        "color_space": "p3",
    }
    path = tmp_path / "roundtrip.avif"
    write_22028_pq(data, str(path))

    img = read_22028_pq(str(path))

    assert img["color_space"] == "p3"
    np.testing.assert_allclose(img["data"], original, atol=0.02)
