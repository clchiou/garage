__all__ = [
    'open_fd',

    'make_bytes_reader',
    'make_packed_bytes_reader',

    'make_file_reader',
    'make_packed_file_reader',

    'make_bytes_builder',

    'make_bytes_writer',
]

import contextlib
import os

from . import native


@contextlib.contextmanager
def _resetting(resource):
    try:
        yield resource
    finally:
        resource._reset()


@contextlib.contextmanager
def open_fd(path, flags):
    fd = os.open(path, flags)
    try:
        yield fd
    finally:
        os.close(fd)


def make_bytes_reader(blob):
    return _resetting(native.FlatArrayMessageReader(blob))


@contextlib.contextmanager
def make_packed_bytes_reader(blob):
    with _resetting(native.ArrayInputStream(blob)) as stream:
        with _resetting(native.PackedMessageReader(stream)) as reader:
            yield reader


@contextlib.contextmanager
def make_file_reader(path):
    with open_fd(path, os.O_RDONLY) as fd:
        with _resetting(native.StreamFdMessageReader(fd)) as reader:
            yield reader


@contextlib.contextmanager
def make_packed_file_reader(path):
    with open_fd(path, os.O_RDONLY) as fd:
        with _resetting(native.PackedFdMessageReader(fd)) as reader:
            yield reader


def make_bytes_builder():
    return _resetting(native.MallocMessageBuilder())


def make_bytes_writer():
    return _resetting(native.VectorOutputStream())
