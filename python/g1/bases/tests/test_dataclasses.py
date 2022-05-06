import unittest

import dataclasses
import typing

from g1.bases import dataclasses as g1_dataclasses


class DataclassesTest(unittest.TestCase):

    def test_fromdict(self):

        @dataclasses.dataclass(frozen=True)
        class Child:
            s: str

        @dataclasses.dataclass(frozen=True)
        class Root:
            i: int
            c: Child
            cs: typing.List[Child]
            nested: typing.List[typing.List[typing.List[Child]]]
            t: typing.Tuple[int, typing.Tuple[str, Child]]
            o: typing.Optional[typing.List[str]]
            d: typing.Mapping[str, Child]
            dm: typing.MutableMapping[int, typing.List[Child]]
            default: str = 'hello world'

        # NOTE: fromdict does not check most of the value types.

        root = Root(
            i='not-integer',
            c=Child(s=0),
            cs=[Child(s=0)],
            nested=[[], [[], [Child(s=0)], [Child(s=1), Child(s=2)]]],
            t=('not-integer', (0, Child(s=0))),
            o=[],
            d={
                'x': Child(s=1),
                'y': Child(s=2),
            },
            dm={'z': [Child(s=3), Child(s=4)]},
        )
        self.assertEqual(
            g1_dataclasses.fromdict(Root, dataclasses.asdict(root)),
            root,
        )

        root = Root(
            i=0,
            c=Child(s=''),
            cs=[],
            nested=[],
            t=(0, ('', Child(s=''))),
            o=None,
            d={},
            dm={},
        )
        self.assertEqual(
            g1_dataclasses.fromdict(Root, dataclasses.asdict(root)),
            root,
        )

        # Extra entries are ignored.
        self.assertEqual(
            g1_dataclasses.fromdict(
                Root,
                {
                    'i': 0,
                    'c': {
                        's': '',
                        'no-such-field': 99,
                    },
                    'cs': [],
                    'nested': [],
                    't': [0, ['', {
                        's': '',
                    }]],
                    'o': None,
                    'no-such-field': 99,
                    'd': {},
                    'dm': {},
                },
            ),
            root,
        )


if __name__ == '__main__':
    unittest.main()
