"""Image manipulation tools."""

__all__ = [
    'ImageError',
    'ImageFormat',
    'detect_format',
    'resize',
    'resize_safe',
]

import enum
import os
import tempfile

from . import _imagetools
from ._imagetools import ImageError
from ._imagetools import resize


@enum.unique
class ImageFormat(enum.Enum):
    FORMAT_UNKNOWN = _imagetools.FORMAT_UNKNOWN
    FORMAT_GIF = _imagetools.FORMAT_GIF
    FORMAT_JPEG = _imagetools.FORMAT_JPEG
    FORMAT_PNG = _imagetools.FORMAT_PNG


def detect_format(image):
    """Detect image format."""
    return ImageFormat(_imagetools.detect_format(image))


def resize_safe(image, desired_width, output_path):
    """Safer version of resize.

    It writes to a temp file while processing, and so does not clobber
    output file on error.
    """
    _, tmp_path = tempfile.mkstemp()
    try:
        dimension = resize(image, desired_width, tmp_path)
        os.rename(tmp_path, output_path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            os.remove(tmp_path)
    return dimension
