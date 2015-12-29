__all__ = [
    'Version',
]

import re
from collections import namedtuple


class Version(namedtuple('Version', 'major minor patch')):

    # Should I forbid leading zeros?
    PATTERN_VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)')

    @classmethod
    def parse(cls, version):
        match = cls.PATTERN_VERSION.fullmatch(version)
        if not match:
            raise ValueError(version)
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def __str__(self):
        return '%d.%d.%d' % self

    def is_compatible_with(self, other):
        return self.major == other.major
