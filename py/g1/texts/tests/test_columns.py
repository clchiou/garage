import unittest

import io

from g1.texts import columns


class ColumnarTest(unittest.TestCase):

    def test_stringifiers(self):
        columnar = columns.Columnar(['x'], stringifiers={'x': hex})
        columnar.append({'x': 0x1})
        columnar.append({'x': 0x12})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'x   \n'
            '0x1 \n'
            '0x12\n',
        )

    def test_column_widths(self):
        columnar = columns.Columnar(['x', 'y'])
        columnar.append({'x': '', 'y': ''})
        columnar.append({'x': '---', 'y': '--'})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'x   y \n'
            '      \n'
            '--- --\n',
        )

        columnar = columns.Columnar(['x', 'y'], header=False)
        columnar.append({'x': '', 'y': ''})
        columnar.append({'x': '---', 'y': '--'})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            '      \n'
            '--- --\n',
        )

        columnar = columns.Columnar(['xxxx', 'yyyyy'])
        columnar.append({'xxxx': '', 'yyyyy': ''})
        columnar.append({'xxxx': '---', 'yyyyy': '--'})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'xxxx yyyyy\n'
            '          \n'
            '---  --   \n',
        )

        columnar = columns.Columnar(['xxxx', 'yyyyy'], header=False)
        columnar.append({'xxxx': '', 'yyyyy': ''})
        columnar.append({'xxxx': '---', 'yyyyy': '--'})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            '      \n'
            '--- --\n',
        )

    def test_sort(self):
        columnar = columns.Columnar(['x'])
        columnar.append({'x': 3})
        columnar.append({'x': 1})
        columnar.append({'x': 2})
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(buffer.getvalue(), 'x\n3\n1\n2\n')

        columnar.sort(key=lambda row: row['x'])
        buffer = io.StringIO()
        columnar.output(buffer)
        self.assertEqual(buffer.getvalue(), 'x\n1\n2\n3\n')

    def test_empty_columns(self):
        for kwargs, expect in (
            (
                {
                    'format': columns.Formats.CSV,
                    'header': False,
                },
                '\r\n',
            ),
            (
                {
                    'format': columns.Formats.CSV,
                    'header': True,
                },
                '\r\n\r\n',
            ),
            (
                {
                    'format': columns.Formats.TEXT,
                    'header': False,
                },
                '\n',
            ),
            (
                {
                    'format': columns.Formats.TEXT,
                    'header': True,
                },
                '\n\n',
            ),
        ):
            with self.subTest(kwargs):
                columnar = columns.Columnar([], **kwargs)
                columnar.append({'x': 1})
                buffer = io.StringIO()
                columnar.output(buffer)
                self.assertEqual(buffer.getvalue(), expect)


if __name__ == '__main__':
    unittest.main()
