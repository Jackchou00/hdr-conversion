"""
Image is basically an array of pixels.

what really matters is the colorspace and type of image.
"""

import numpy as np
from colour import RGB_Colourspace
from enum import Enum, auto
import colour


BT2020_Linear = RGB_Colourspace(
    name="BT.2020 Linear",
    primaries=((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),
    whitepoint=(0.3127, 0.3290),
    whitepoint_name="D65",
    cctf_decoding=colour.linear_function,
    cctf_encoding=colour.linear_function,
    use_derived_matrix_RGB_to_XYZ=True,
    use_derived_matrix_XYZ_to_RGB=True,
)


class ImageType(Enum):
    SDR = auto()
    HDR = auto()
    GAINMAP = auto()


class Image:
    """
    Args:
        content (np.ndarray): The pixel data of the image.
        colorspace (RGB_Colourspace): The colorspace of the image.
        image_type (ImageType): The type of image (e.g., 'SDR', 'HDR', 'GAINMAP').
    """

    def __init__(
        self, content: np.ndarray, colorspace: RGB_Colourspace, image_type: ImageType
    ) -> None:
        # check content is a 2d or 3d array
        if not isinstance(content, np.ndarray) or content.ndim not in (2, 3):
            raise ValueError("Content must be a 2D or 3D numpy array.")
        # TODO: maybe should add a default colorspace and image_type instead of raising error
        if not isinstance(colorspace, RGB_Colourspace):
            raise ValueError("Colorspace must be an instance of RGB_Colourspace.")
        if not isinstance(image_type, ImageType):
            raise ValueError("Image type must be an instance of ImageType Enum.")
        self.content: np.ndarray = content
        self.colorspace: RGB_Colourspace = colorspace
        self.image_type: ImageType = image_type

    @property
    def shape(self) -> tuple:
        return self.content.shape

    def __repr__(self) -> str:
        return f"Image(type={self.image_type}, shape={self.shape}, colorspace={self.colorspace.name})"


class InterMediateImage(Image):
    """
    An intermediate image used in processing pipelines.
    """

    def __init__(self, content: np.ndarray) -> None:
        super().__init__(content, colorspace=BT2020_Linear, image_type=ImageType.HDR)


class ImageContainer:
    """
    A container for multiple images, such as an SDR image and its corresponding gainmap.
    """

    def __init__(self, images: list[Image], metadata=None) -> None:
        if not all(isinstance(img, Image) for img in images):
            raise ValueError("All items in images must be instances of Image.")
        self.images = images
        self.metadata = metadata or {}
