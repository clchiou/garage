"""Image manipulation tools."""

__all__ = [

    'ImageError',
    'Unsupported',

    'ImageFormat',
    'detect_format',
    'resize',
    'resize_unsafe',
]

import enum
import os
import tempfile

from . import _imagetools
from ._imagetools import ImageError


class Unsupported(ImageError):
    pass


@enum.unique
class ImageFormat(enum.Enum):
    UNKNOWN = _imagetools.FORMAT_UNKNOWN
    GIF = _imagetools.FORMAT_GIF
    JPEG = _imagetools.FORMAT_JPEG
    PNG = _imagetools.FORMAT_PNG


def detect_format(image):
    """Detect image format."""
    return ImageFormat(_imagetools.detect_format(image))


def resize(image, desired_width, output_path):
    """Resize an image to the desired_width.

    It writes to a temporary file while processing, and so it does not
    clobber output file on error.  If clobbering output is not an issue,
    you may use resize_unsafe, which is faster.
    """

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)  # Close fd immediately (don't leak it!).

        dimension = resize_unsafe(image, desired_width, tmp_path)
        os.rename(tmp_path, output_path)
        tmp_path = None

    finally:
        if tmp_path is not None:
            os.remove(tmp_path)

    return dimension


def resize_unsafe(image, desired_width, output_path):
    """Unsafe version of resize."""
    image_format = detect_format(image)
    if image_format is ImageFormat.JPEG:
        return _imagetools.resize_jpeg(image, desired_width, output_path)
    else:
        raise Unsupported
