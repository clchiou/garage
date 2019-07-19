"""Converter between (variable name) case styles."""

__all__ = [
    'camel_to_lower_snake',
    'lower_snake_to_lower_camel',
    'lower_snake_to_upper_camel',
    'upper_to_lower_camel',
]

import re

from g1.bases.assertions import ASSERT

_CAMEL_TO_LOWER_SNAKE_PATTERN = re.compile(r'(?<!_)[A-Z](?:[a-z]|$)')


def camel_to_lower_snake(camel):
    snake = _CAMEL_TO_LOWER_SNAKE_PATTERN.sub(
        lambda match: (
            '_' + match.group(0) if match.start(0) > 0 else match.group(0)
        ),
        camel,
    )
    return snake.lower()


_LOWER_SNAKE_TO_LOWER_CAMEL_PATTERN = re.compile(r'_+([a-z0-9])')


def lower_snake_to_lower_camel(snake):
    return _LOWER_SNAKE_TO_LOWER_CAMEL_PATTERN.sub(
        lambda match: (
            match.group(1).upper() if match.start(0) > 0 else
            match.group(0)
        ),
        ASSERT.predicate(snake, str.islower),
    )


_LOWER_SNAKE_TO_UPPER_CAMEL_PATTERN = re.compile(r'(?:^|_+)([a-z0-9])')


def lower_snake_to_upper_camel(snake):
    return _LOWER_SNAKE_TO_UPPER_CAMEL_PATTERN.sub(
        lambda match: (
            match.group(1).upper() if match.start(0) > 0 else
            match.group(0).upper()
        ),
        ASSERT.predicate(snake, str.islower),
    )


_UPPER_TO_LOWER_CAMEL_PATTERN = re.compile(r'^_*[A-Z]')


def upper_to_lower_camel(camel):
    return _UPPER_TO_LOWER_CAMEL_PATTERN.sub(
        lambda match: match.group(0).lower(), camel
    )
