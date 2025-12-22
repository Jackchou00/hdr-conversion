import numpy as np
import cv2


def to_alternate(
    baseline_image: np.ndarray, gainmap_image: np.ndarray, gainmap_metadata: dict
) -> np.ndarray:
    """
    Convert a baseline image and gainmap image to an alternate representation
    according to ISO 21496 standard.

    Parameters:
    - baseline_image: A numpy array representing the baseline image.
        Expected to be normalized to [0.0, 1.0] range.
    - gainmap_image: A numpy array representing the gainmap image.
        Expected to be normalized to [0.0, 1.0] range.
    - gainmap_metadata: A dictionary containing metadata for the gainmap.

    Returns:
    - A numpy array representing the alternate image in linear domain.
    """

    # Get image dimensions
    h, w = baseline_image.shape[:2]

    # Resize gainmap if dimensions don't match
    if gainmap_image.shape[:2] != (h, w):
        gainmap = cv2.resize(gainmap_image, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        gainmap = gainmap_image

    # Ensure float32 for calculations
    gainmap = gainmap.astype(np.float32)
    baseline = baseline_image.astype(np.float32)

    # Get metadata values and convert to numpy arrays for proper broadcasting
    gainmap_min = np.array(gainmap_metadata.get("gainmap_min"), dtype=np.float32)
    gainmap_max = np.array(gainmap_metadata.get("gainmap_max"), dtype=np.float32)
    gainmap_gamma = np.array(gainmap_metadata.get("gainmap_gamma"), dtype=np.float32)
    baseline_offset = np.array(gainmap_metadata.get("baseline_offset"), dtype=np.float32)
    alternate_offset = np.array(gainmap_metadata.get("alternate_offset"), dtype=np.float32)


    gainmap = np.clip(gainmap, 0.0, 1.0)
    gainmap = gainmap ** gainmap_gamma
    gainmap = gainmap * (gainmap_max - gainmap_min) + gainmap_min
    gainmap_linear = np.exp2(gainmap)
    alternate_image = gainmap_linear * (baseline + baseline_offset) - alternate_offset

    return alternate_image
