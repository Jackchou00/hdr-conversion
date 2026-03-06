from itertools import permutations
from pathlib import Path

import colour
import numpy as np

from hdrconv.icc.colorconvert import (
    build_icc_conversion_matrix,
    convert_array_with_icc_matrix,
    read_icc_primaries_matrix,
    read_icc_whitepoint,
)


ICC_DIR = Path(__file__).resolve().parents[1] / "icc"
ICC_FILES = sorted(ICC_DIR.glob("*.icc"))
SAMPLE_RGB = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.25, 0.5, 0.75],
        [0.9, 0.1, 0.3],
    ],
    dtype=np.float32,
)


def _xyz_to_xy(xyz: np.ndarray) -> np.ndarray:
    xyz = np.asarray(xyz, dtype=np.float64)
    total = xyz.sum(axis=-1, keepdims=True)
    return xyz[..., :2] / total


def _build_colourspace(icc_file: Path) -> colour.RGB_Colourspace:
    matrix_rgb_to_xyz = read_icc_primaries_matrix(icc_file)
    primaries = _xyz_to_xy(matrix_rgb_to_xyz.T)
    whitepoint = _xyz_to_xy(read_icc_whitepoint(icc_file)).reshape(2)

    return colour.RGB_Colourspace(
        name=icc_file.stem,
        primaries=primaries,
        whitepoint=whitepoint,
        matrix_RGB_to_XYZ=matrix_rgb_to_xyz,
        matrix_XYZ_to_RGB=np.linalg.inv(matrix_rgb_to_xyz),
    )


def test_build_icc_conversion_matrix_matches_colour_science_truth():
    for source_icc, target_icc in permutations(ICC_FILES, 2):
        source_colourspace = _build_colourspace(source_icc)
        target_colourspace = _build_colourspace(target_icc)

        expected_matrix = colour.matrix_RGB_to_RGB(
            source_colourspace,
            target_colourspace,
            chromatic_adaptation_transform=None,
        )
        actual_matrix = build_icc_conversion_matrix(source_icc, target_icc)

        np.testing.assert_allclose(
            actual_matrix,
            expected_matrix,
            rtol=1e-7,
            atol=1e-7,
            err_msg=f"matrix mismatch: {source_icc.name} -> {target_icc.name}",
        )


def test_convert_array_with_icc_matrix_matches_colour_science_truth():
    for source_icc, target_icc in permutations(ICC_FILES, 2):
        source_colourspace = _build_colourspace(source_icc)
        target_colourspace = _build_colourspace(target_icc)
        expected_matrix = colour.matrix_RGB_to_RGB(
            source_colourspace,
            target_colourspace,
            chromatic_adaptation_transform=None,
        )
        expected_rgb = SAMPLE_RGB @ expected_matrix.T

        actual_rgb = convert_array_with_icc_matrix(source_icc, target_icc, SAMPLE_RGB)

        np.testing.assert_allclose(
            actual_rgb,
            expected_rgb,
            rtol=1e-6,
            atol=1e-6,
            err_msg=f"array mismatch: {source_icc.name} -> {target_icc.name}",
        )
